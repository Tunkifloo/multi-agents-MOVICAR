"""n8n_deploy.py · Construye y despliega los flujos de MOVICAR en n8n.

workflows/*.json es la FUENTE (versionada). Este script:
  1. Inyecta en cada flujo: scripts/lib/contrato.js (__CONTRATO__), prompts/*.md (__PROMPT:nombre__),
     constantes de config/reglas.json (__UMBRAL_CONFIANZA__, __DIAS_MAX_ANTICIPACION__, __SLA_REVISION_HORAS__,
     __SEGUIMIENTO_HORAS__, __TRANSICIONES__, __ESTADOS_COTIZABLES__, __ESTADOS_RESERVABLES__),
     IDs de Data Tables (__DT:nombre__) desde config/n8n_ids.json e IDs de subflujos (__WF:nombre__).
  2. Escribe el resultado en build/ (importable a mano si la API no está disponible).
  3. Con --push, crea o actualiza cada flujo por nombre en n8n (API pública) en el orden de config/n8n_ids.json → orden_despliegue.
  4. Con --activar, activa los flujos listados en orden_despliegue con "activar": true.

Requiere .env con N8N_URL (https://xxx.app.n8n.cloud) y N8N_API_KEY.
Uso:  python scripts/n8n_deploy.py            (solo build/)
      python scripts/n8n_deploy.py --push --activar
Antes de construir ejecuta verificar_flujo.py y aborta si hay errores.
"""
import argparse, json, os, re, subprocess, sys, urllib.request, urllib.error
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BUILD = RAIZ / "build"

def cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def api(metodo, ruta, cuerpo=None):
    url = os.environ["N8N_URL"].rstrip("/") + "/api/v1" + ruta
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    req = urllib.request.Request(url, data=datos, method=metodo, headers={
        "X-N8N-API-KEY": os.environ["N8N_API_KEY"], "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        sys.exit(f"API {metodo} {ruta} → {e.code}: {e.read().decode(errors='replace')[:800]}")

def js_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)[1:-1]  # escapar para incrustar dentro de un string JSON

def construir(ids):
    reglas = json.loads((RAIZ / "config/reglas.json").read_text(encoding="utf-8"))
    contrato = (RAIZ / "scripts/lib/contrato.js").read_text(encoding="utf-8")
    contrato = contrato.replace("if (typeof module !== 'undefined') module.exports = { validarContrato, calcularClave };", "")
    contrato = contrato.replace("__DIAS_MAX_ANTICIPACION__", str(reglas["DIAS_MAX_ANTICIPACION"]))
    BUILD.mkdir(exist_ok=True)
    salida = {}
    for f in sorted((RAIZ / "workflows").glob("*.json")):
        t = f.read_text(encoding="utf-8")
        t = t.replace("__CONTRATO__", js_str(contrato))
        for m in set(re.findall(r"__PROMPT:([a-z_]+)__", t)):
            prompt = (RAIZ / "prompts" / f"{m}.md").read_text(encoding="utf-8").strip()
            t = t.replace(f"__PROMPT:{m}__", js_str(prompt))
        constantes = {
            "__UMBRAL_CONFIANZA__": str(reglas["UMBRAL_CONFIANZA"]),
            "__DIAS_MAX_ANTICIPACION__": str(reglas["DIAS_MAX_ANTICIPACION"]),
            "__SLA_REVISION_HORAS__": str(reglas["SLA_REVISION_HORAS"]),
            "__SEGUIMIENTO_HORAS__": str(reglas["SEGUIMIENTO_HORAS"]),
            "__TRANSICIONES__": js_str(json.dumps(reglas["transiciones"], ensure_ascii=False)),
            "__ESTADOS_COTIZABLES__": js_str(json.dumps(reglas["estados_cotizables"])),
            "__ESTADOS_RESERVABLES__": js_str(json.dumps(reglas["estados_reservables"])),
        }
        for k, v in constantes.items():
            t = t.replace(k, v)
        for nombre, dt_id in ids.get("data_tables", {}).items():
            t = t.replace(f"__DT:{nombre}__", dt_id)
        for nombre, wf_id in ids.get("workflows", {}).items():
            t = t.replace(f"__WF:{nombre}__", wf_id)
        pendientes = sorted(set(re.findall(r"__[A-Z]+(?::[a-z_]+)?__", t)))
        d = json.loads(t)
        (BUILD / f.name).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        salida[d["name"]] = (f.name, d, pendientes)
    return salida

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--activar", action="store_true")
    a = ap.parse_args()
    cargar_env()
    r = subprocess.run([sys.executable, str(RAIZ / "scripts/verificar_flujo.py")])
    if r.returncode != 0:
        sys.exit("verificar_flujo.py encontró errores: no se despliega.")
    ids_path = RAIZ / "config/n8n_ids.json"
    ids = json.loads(ids_path.read_text(encoding="utf-8")) if ids_path.exists() else {}
    flujos = construir(ids)
    for nombre, (archivo, _, pend) in flujos.items():
        print(f"build/{archivo}: {nombre}" + (f"  · marcadores sin resolver: {pend}" if pend else ""))
    if not a.push:
        return
    existentes = {w["name"]: w["id"] for w in api("GET", "/workflows?limit=250").get("data", [])}
    orden = ids.get("orden_despliegue", [{"nombre": n} for n in flujos])
    for paso in orden:
        nombre = paso["nombre"]
        if nombre not in flujos:
            print(f"(omitido) {nombre}: no existe en workflows/"); continue
        # reconstruir: los subflujos recién creados pueden haber resuelto __WF:...__
        flujos = construir(ids)
        archivo, d, pend = flujos[nombre]
        if pend:
            sys.exit(f"{nombre}: marcadores sin resolver {pend}. Complete config/n8n_ids.json.")
        cuerpo = {k: d[k] for k in ("name", "nodes", "connections") if k in d}
        cuerpo["settings"] = {k: v for k, v in d.get("settings", {}).items()
                              if k in ("executionOrder", "timezone", "errorWorkflow", "saveManualExecutions",
                                       "saveDataErrorExecution", "saveDataSuccessExecution", "callerPolicy")}
        if nombre in existentes:
            wid = existentes[nombre]; api("PUT", f"/workflows/{wid}", cuerpo); print(f"actualizado  {nombre} ({wid})")
        else:
            wid = api("POST", "/workflows", cuerpo)["id"]; existentes[nombre] = wid; print(f"creado       {nombre} ({wid})")
        if paso.get("clave_wf"):
            ids.setdefault("workflows", {})[paso["clave_wf"]] = wid
            ids_path.write_text(json.dumps(ids, ensure_ascii=False, indent=2), encoding="utf-8")
        if a.activar and paso.get("activar"):
            api("POST", f"/workflows/{wid}/activate"); print(f"activado     {nombre}")

if __name__ == "__main__":
    main()
