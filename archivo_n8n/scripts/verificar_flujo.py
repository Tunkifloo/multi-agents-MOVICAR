"""verificar_flujo.py · Chequeo determinista de los flujos n8n de MOVICAR.

Uso:
  python scripts/verificar_flujo.py                 # revisa workflows/*.json
  python scripts/verificar_flujo.py archivo.json    # revisa un archivo
  (como hook de Claude Code lee el JSON del evento por stdin y revisa el archivo editado)

Sale con código 2 si hay errores (Claude Code muestra stderr al modelo y debe corregir).
Reglas: ver docs/ARQUITECTURA.md §4–§8 y CLAUDE.md «Reglas que protegen lo crítico».
"""
import json, re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SECRETOS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "API key de Google"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "API key tipo sk-"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{20,}"), "token Bearer"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "JWT"),
    (re.compile(r'(?i)"(password|apiKey|api_key|secret|x-test-token)"\s*:\s*"[^"_]{6,}"'), "secreto en texto plano"),
]
ESCRITURA = {"insert", "update", "upsert", "delete", "deleteRows"}
FROMAI_PROHIBIDO = {
    "estado": "el estado lo decide el código, no la IA",
    "session_id": "session_id se inyecta desde el trigger",
    "precio_unitario": "el precio se lee del catálogo",
    "precio": "el precio se lee del catálogo",
    "stock": "el stock se lee del catálogo",
    "total": "el total lo calcula sw_cotizar",
    "total_cotizacion": "el total lo calcula sw_cotizar",
    "especialidad_turno": "la especialidad del turno se toma de la solicitud",
}
AUTH_REQUERIDA = ("Pendientes", "Bandeja", "Utilidad")

def nodos(d):
    return [n for n in d.get("nodes", []) if n.get("type") != "n8n-nodes-base.stickyNote"]

def conectados_como_tool(d):
    out = set()
    for origen, salidas in d.get("connections", {}).items():
        if "ai_tool" in salidas:
            out.add(origen)
    return out

def revisar(path: Path):
    errores, avisos = [], []
    texto = path.read_text(encoding="utf-8")
    try:
        d = json.loads(texto)
    except json.JSONDecodeError as e:
        return [f"JSON inválido: {e}"], []
    nombre = d.get("name", path.stem)

    for rx, desc in SECRETOS:
        if rx.search(texto):
            errores.append(f"posible {desc} en el archivo")
    if '"credentials"' in texto:
        avisos.append("contiene referencias a credenciales (id/nombre). Es aceptable, pero no deben ir claves.")

    tools = conectados_como_tool(d)
    for n in nodos(d):
        t, p, nm = n.get("type", ""), n.get("parameters", {}), n.get("name", "")
        sp = json.dumps(p, ensure_ascii=False)
        # 1. Ningún agente escribe directo en una Data Table
        if t.endswith("dataTableTool") and p.get("operation") in ESCRITURA:
            errores.append(f"[{nm}] Data Table Tool con operación '{p.get('operation')}': los agentes solo pueden leer; las escrituras van por un subflujo sw_*")
        # 2. $fromAI prohibidos
        for campo, motivo in FROMAI_PROHIBIDO.items():
            if re.search(r"\$fromAI\(\s*['\"]" + re.escape(campo) + r"['\"]", sp):
                errores.append(f"[{nm}] $fromAI('{campo}') no permitido: {motivo}")
        # 2b. Ninguna herramienta recibe precio o stock desde la IA (esquema de entrada)
        if t.endswith("toolCode") or t.endswith("toolWorkflow"):
            esquema = json.dumps(p.get("inputSchema", "")) + json.dumps(p.get("workflowInputs", {}))
            if re.search(r"precio|stock", esquema, re.I):
                errores.append(f"[{nm}] la herramienta recibe precio o stock desde la IA; debe recibir solo codigo y cantidad")
        # 3. Umbral y constantes no escritas a mano en el código fuente
        if t.endswith(".code") or t.endswith("toolCode"):
            code = p.get("jsCode", "")
            if re.search(r"confianza[^\n]{0,40}(<|>=?)\s*0?\.9\d*", code):
                errores.append(f"[{nm}] umbral de confianza escrito a mano; usar __UMBRAL_CONFIANZA__ (config/reglas.json)")
            if "validarContrato" in code and "__CONTRATO__" not in code and "function validarContrato" not in code:
                errores.append(f"[{nm}] usa validarContrato sin incluir scripts/lib/contrato.js (marcador __CONTRATO__)")
        # 4. Autenticación en formularios y webhooks no públicos
        if t in ("n8n-nodes-base.formTrigger", "n8n-nodes-base.webhook") and any(k in nombre for k in AUTH_REQUERIDA):
            auth = p.get("authentication") or p.get("options", {}).get("authentication")
            if auth in (None, "none"):
                errores.append(f"[{nm}] {t.split('.')[-1]} sin autenticación en un flujo que no es público")
        # 5. Agentes: maxIterations razonable
        if t.endswith("langchain.agent"):
            mi = p.get("options", {}).get("maxIterations", 10)
            if mi < 15:
                avisos.append(f"[{nm}] maxIterations={mi}; una cotización completa usa ~10 llamadas, se recomienda ≥ 15")
    # 6. Error workflow configurado en el asistente
    if "Asistente" in nombre and not d.get("settings", {}).get("errorWorkflow"):
        errores.append("el flujo del Asistente no tiene errorWorkflow configurado")
    # 7. Trazabilidad: cada nodo debe figurar en docs/TRAZABILIDAD.md
    traz = RAIZ / "docs" / "TRAZABILIDAD.md"
    if traz.exists():
        contenido = traz.read_text(encoding="utf-8")
        faltan = [n["name"] for n in nodos(d) if n["name"] not in contenido]
        if faltan:
            errores.append("nodos sin fila en docs/TRAZABILIDAD.md: " + ", ".join(faltan))
    return errores, avisos

def archivos_desde_stdin():
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.read().strip()
    if not raw:
        return None
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        return None
    fp = (ev.get("tool_input") or {}).get("file_path", "")
    if fp.replace("\\", "/").find("/workflows/") >= 0 and fp.endswith(".json"):
        return [Path(fp)]
    return []  # evento de un archivo que no es un flujo: nada que revisar

def main():
    if len(sys.argv) > 1:
        archivos = [Path(a) for a in sys.argv[1:]]
    else:
        archivos = archivos_desde_stdin()
        if archivos is None:
            archivos = sorted((RAIZ / "workflows").glob("*.json"))
    hay_error = False
    for f in archivos:
        if not f.exists():
            continue
        errores, avisos = revisar(f)
        for a in avisos:
            print(f"AVISO  {f.name}: {a}", file=sys.stderr)
        for e in errores:
            print(f"ERROR  {f.name}: {e}", file=sys.stderr)
        hay_error |= bool(errores)
        if not errores:
            print(f"OK     {f.name}")
    sys.exit(2 if hay_error else 0)

if __name__ == "__main__":
    main()
