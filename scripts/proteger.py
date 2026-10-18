"""proteger.py · Hook PreToolUse de Claude Code.

Bloquea la edición directa de los elementos protegidos. El agente debe PROPONER el cambio
(diff en el chat) y esperar aprobación humana. Sale con 2 para bloquear.
"""
import json, sys

PROTEGIDOS = {
    "config/reglas.json": "umbral de confianza, plazos y transiciones de estado",
    "datos/catalogo_servicios.csv": "tarifario y stock (los define el taller)",
    "tests/escenarios.json": "banco de pruebas (no se debilita una prueba para que pase)",
    "scripts/lib/contrato.js": "contrato de entrada del Lab 02",
    "scripts/verificar_flujo.py": "controles automáticos",
    "scripts/proteger.py": "controles automáticos",
}

try:
    ev = json.loads(sys.stdin.read() or "{}")
except json.JSONDecodeError:
    sys.exit(0)
fp = ((ev.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
for ruta, motivo in PROTEGIDOS.items():
    if fp.endswith(ruta):
        print(f"BLOQUEADO: '{ruta}' es un elemento protegido ({motivo}). "
              "No lo edites directamente: muestra el diff propuesto, explica por qué y espera la aprobación del equipo.",
              file=sys.stderr)
        sys.exit(2)
sys.exit(0)
