"""verificar_codigo.py · Controles deterministas de la arquitectura LangChain de MOVICAR (hook PostToolUse).

Uso:
  python scripts/verificar_codigo.py            # revisa todo el proyecto
  (como hook de Claude Code lee el evento por stdin y revisa solo el archivo editado)

Reglas (ver docs/ARQUITECTURA.md):
  1. Sin secretos en archivos versionables (claves de Google AI Studio, tokens).
  2. Los agentes (backend/app/agentes/) NO acceden a la base de datos: solo llaman a app/servicios.
  3. El umbral de confianza y los plazos no se escriben a mano: se leen de config/reglas.json.
  4. Ninguna herramienta expone al modelo argumentos prohibidos (estado, session_id, precio, stock, total).
Sale con código 2 si hay errores (Claude Code muestra stderr y debe corregir).
"""
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SECRETOS = [
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "API key de Google"),
    (re.compile(r"AQ\.[0-9A-Za-z_\-]{30,}"), "API key de Google AI Studio"),
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "API key tipo sk-"),
    (re.compile(r"lsv2_[A-Za-z0-9_]{20,}"), "API key de LangSmith"),
]
ARG_PROHIBIDOS = ("estado", "session_id", "precio", "precio_unitario", "stock", "total", "total_cotizacion")
EXCLUIR = ("/.venv/", "/node_modules/", "/dist/", "/archivo_n8n/", "/tests/resultados/", "/backend/data/")


def revisar(f: Path) -> list[str]:
    rel = "/" + f.relative_to(RAIZ).as_posix()
    if any(x in rel for x in EXCLUIR) or f.name.startswith(".env"):
        return []
    try:
        texto = f.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    errores = [f"{nombre} en texto plano" for rx, nombre in SECRETOS if rx.search(texto)]
    if rel.startswith("/backend/app/agentes/") and f.suffix == ".py":
        if re.search(r"^\s*(from|import)\s+(sqlalchemy|\.\.db\b|app\.db\b)", texto, re.M):
            errores.append("un agente importa la base de datos: debe usar app/servicios (capa determinista)")
        for m in re.finditer(r"@tool[^\n]*\n(?:async\s+)?def\s+\w+\(([^)]*)\)", texto, re.S):
            params = re.findall(r"(\w+)\s*:", m.group(1))
            malos = [p for p in params if p in ARG_PROHIBIDOS]
            if malos:
                errores.append(f"herramienta expone al modelo argumentos prohibidos: {', '.join(malos)}")
    if (rel.startswith("/backend/app/") or rel.startswith("/prompts/")) and f.suffix in (".py", ".md"):
        if re.search(r"(umbral|UMBRAL)[^\n]{0,40}=\s*0[.,]9\b", texto):
            errores.append("umbral de confianza escrito a mano: léalo de config/reglas.json")
    return errores


def archivos_desde_stdin():
    if sys.stdin.isatty():
        return None
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    try:
        fp = (json.loads(raw).get("tool_input") or {}).get("file_path", "")
    except json.JSONDecodeError:
        return None
    p = Path(fp)
    return [p] if fp and p.exists() and RAIZ in p.resolve().parents else []


def main():
    archivos = archivos_desde_stdin()
    if archivos is None:
        archivos = []
        for carpeta, subcarpetas, nombres in os.walk(RAIZ):
            subcarpetas[:] = [s for s in subcarpetas if s not in (".venv", "node_modules", "dist", ".git", "archivo_n8n", "data")]
            archivos += [Path(carpeta) / n for n in nombres
                         if Path(n).suffix in (".py", ".md", ".ts", ".tsx", ".json", ".yml", ".txt")]
    hay_error = False
    for f in archivos:
        for e in revisar(f.resolve()):
            print(f"ERROR  {f.relative_to(RAIZ) if RAIZ in f.resolve().parents else f}: {e}", file=sys.stderr)
            hay_error = True
    if not hay_error:
        print(f"OK     {len(archivos)} archivo(s) revisado(s)")
    sys.exit(2 if hay_error else 0)


if __name__ == "__main__":
    main()
