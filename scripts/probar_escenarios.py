"""probar_escenarios.py · Ejecuta el banco de conversaciones de cliente (tests/escenarios.json).

Uso:
  python scripts/probar_escenarios.py                  # todos
  python scripts/probar_escenarios.py E01 E04          # algunos
  python scripts/probar_escenarios.py --repeticiones 3 # estabilidad (el LLM no es determinista)

Cada paso puede ser:
  {"cliente": "texto", "espera": ["regex", ...], "no_espera": ["regex", ...]}
  {"util": "accion", ...params}                         # utilidad de pruebas
  {"estado": "cotizada", "campos": {"total_cotizacion": 355}}   # verifica la fila de la sesión
  {"sin_fila": true}                                   # verifica que NO se creó fila
Marcadores en textos y parámetros:
  {{dia:+N}}  → fecha hábil (no domingo) a N días, en texto: "lunes 19 de octubre"
  {{iso:+N}}  → la misma en AAAA-MM-DD
  {{sabado}} / {{domingo}} → próximo sábado o domingo en texto · {{tel}} → teléfono de prueba único (+5190000xxxx)
  {{clave}}, {{turno_1}} … → capturados de la fila tras un paso "estado"
  {"nueva_sesion": true} → cambia de sesión (otro cliente) · {"cuenta": 1} → filas de la sesión actual
Salida: tabla en consola + tests/resultados/AAAAMMDD-HHMM.md y .json
"""
import argparse, json, random, re, sys, time, uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente_api import cargar_env, enviar_mensaje, utilidad

RAIZ = Path(__file__).resolve().parent.parent
DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def hoy_lima():
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()

def habil(n):
    d = hoy_lima() + timedelta(days=n)
    return d + timedelta(days=1) if d.weekday() == 6 else d

def texto_fecha(d):
    return f"{DIAS[d.weekday()]} {d.day} de {MESES[d.month - 1]}"

def expandir(valor, ctx):
    if isinstance(valor, dict):
        return {k: expandir(v, ctx) for k, v in valor.items()}
    if isinstance(valor, list):
        return [expandir(v, ctx) for v in valor]
    if not isinstance(valor, str):
        return valor
    valor = re.sub(r"\{\{dia:\+(\d+)\}\}", lambda m: texto_fecha(habil(int(m.group(1)))), valor)
    valor = re.sub(r"\{\{iso:\+(\d+)\}\}", lambda m: habil(int(m.group(1))).isoformat(), valor)
    sab = hoy_lima() + timedelta(days=(5 - hoy_lima().weekday()) % 7 or 7)
    valor = valor.replace("{{sabado}}", texto_fecha(sab)).replace("{{sabado_iso}}", sab.isoformat())
    dom = hoy_lima() + timedelta(days=(6 - hoy_lima().weekday()) % 7 or 7)
    valor = valor.replace("{{domingo}}", texto_fecha(dom))
    for k, v in ctx.items():
        valor = valor.replace("{{" + k + "}}", str(v))
    return valor

def capturar(fila, ctx):
    ctx["clave"] = fila.get("clave", "")
    try:
        turnos = json.loads(fila.get("turnos_propuestos") or "[]")
        for i, t in enumerate(turnos, 1):
            ctx[f"turno_{i}"] = t.get("turno_id", "")
    except (json.JSONDecodeError, TypeError, AttributeError):
        pass

def correr(esc):
    ctx = {"tel": f"90000{random.randint(1000, 9999)}"}  # → +5190000xxxx (lo limpia «reset»)
    sesion = f"test-{esc['id']}-{uuid.uuid4().hex[:6]}"
    ctx["sesion"] = sesion
    log, fallos, t_total = [], [], 0.0
    for i, paso in enumerate(esc["pasos"], 1):
        paso = expandir(paso, ctx)
        if paso.get("nueva_sesion"):
            sesion = f"test-{esc['id']}-{uuid.uuid4().hex[:6]}"; ctx["sesion"] = sesion
            log.append({"paso": i, "util": "nueva_sesion", "params": {}, "resultado": sesion}); continue
        if "cuenta" in paso:
            n = utilidad("contar", session_id=sesion).get("n")
            if n != paso["cuenta"]:
                fallos.append(f"paso {i}: filas de la sesión = {n} ≠ {paso['cuenta']}")
            log.append({"paso": i, "util": "contar", "params": {}, "resultado": n}); continue
        if "cliente" in paso:
            resp, seg = enviar_mensaje(sesion, paso["cliente"])
            t_total += seg
            log.append({"paso": i, "cliente": paso["cliente"], "asistente": resp, "seg": seg})
            for rx in paso.get("espera", []):
                if not re.search(rx, resp, re.I | re.S):
                    fallos.append(f"paso {i}: la respuesta no contiene /{rx}/")
            for rx in paso.get("no_espera", []):
                if re.search(rx, resp, re.I | re.S):
                    fallos.append(f"paso {i}: la respuesta contiene lo prohibido /{rx}/")
        elif "util" in paso:
            params = {k: v for k, v in paso.items() if k != "util"}
            r = utilidad(paso["util"], **params)
            log.append({"paso": i, "util": paso["util"], "params": params, "resultado": r})
        elif "estado" in paso or "sin_fila" in paso:
            fila = utilidad("get_solicitud", session_id=sesion)
            fila = fila if isinstance(fila, dict) else {}
            if paso.get("sin_fila"):
                if fila.get("clave"):
                    fallos.append(f"paso {i}: se esperaba que NO existiera fila y existe ({fila.get('estado')})")
            else:
                capturar(fila, ctx)
                if fila.get("estado") != paso["estado"]:
                    fallos.append(f"paso {i}: estado '{fila.get('estado')}' ≠ esperado '{paso['estado']}'")
                for campo, esperado in paso.get("campos", {}).items():
                    real = fila.get(campo)
                    if str(real).lower() != str(esperado).lower() and not (isinstance(esperado, (int, float)) and _num(real) == esperado):
                        fallos.append(f"paso {i}: {campo}={real!r} ≠ {esperado!r}")
            log.append({"paso": i, "verifica": paso, "fila": {k: fila.get(k) for k in ("clave", "estado", "tipo_servicio_agente", "confianza_agente", "especialidad", "total_cotizacion")}})
        time.sleep(paso.get("pausa", 0) if isinstance(paso, dict) else 0)
    return {"id": esc["id"], "nombre": esc["nombre"], "ok": not fallos, "fallos": fallos, "seg": round(t_total, 1), "sesion": sesion, "log": log}

def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--repeticiones", type=int, default=1)
    a = ap.parse_args()
    cargar_env()
    escenarios = json.loads((RAIZ / "tests/escenarios.json").read_text(encoding="utf-8"))["escenarios"]
    if a.ids:
        escenarios = [e for e in escenarios if e["id"] in a.ids]
    resultados = []
    for esc in escenarios:
        for rep in range(a.repeticiones):
            print(f"▶ {esc['id']} {esc['nombre']} (rep {rep + 1})", flush=True)
            r = correr(esc); resultados.append(r)
            print(("   ✔ OK" if r["ok"] else "   ✘ FALLA") + f"  ({r['seg']} s)")
            for f in r["fallos"]:
                print("     -", f)
    ok = sum(r["ok"] for r in resultados)
    print(f"\n{ok}/{len(resultados)} ejecuciones OK")
    out = RAIZ / "tests/resultados"; out.mkdir(parents=True, exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M")
    (out / f"{marca}.json").write_text(json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# Resultados {marca}", "", f"**{ok}/{len(resultados)} OK**", "", "| Escenario | Resultado | Tiempo | Fallos |", "|---|---|---|---|"]
    md += [f"| {r['id']} {r['nombre']} | {'OK' if r['ok'] else 'FALLA'} | {r['seg']} s | {'; '.join(r['fallos'])} |" for r in resultados]
    md += ["", "## Conversaciones", ""]
    for r in resultados:
        md.append(f"### {r['id']} · {r['nombre']} · sesión `{r['sesion']}`")
        for p in r["log"]:
            if "cliente" in p:
                md += [f"**Cliente:** {p['cliente']}", "", f"**MOVICAR ({p['seg']} s):** {p['asistente']}", ""]
            elif "util" in p:
                md.append(f"_util `{p['util']}` → {json.dumps(p['resultado'], ensure_ascii=False)[:200]}_\n")
            else:
                md.append(f"_fila: {json.dumps(p['fila'], ensure_ascii=False)}_\n")
    (out / f"{marca}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"Informe: tests/resultados/{marca}.md")
    sys.exit(0 if ok == len(resultados) else 1)

if __name__ == "__main__":
    main()
