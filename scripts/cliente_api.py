"""Cliente HTTP mínimo para el API de MOVICAR (solo biblioteca estándar).

Reemplaza a n8n_cliente.py: el canal ya no es el chat de n8n sino el API propio (FastAPI).
Variables (.env o entorno):
  MOVICAR_API_URL  (por defecto http://localhost:8088/api, la interfaz en Docker; en local: http://localhost:8000/api)
  TEST_TOKEN       token de la utilidad de pruebas (requiere MODO_PRUEBAS=true en el API)
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _base():
    return os.environ.get("MOVICAR_API_URL", "http://localhost:8088/api").rstrip("/")


def _post(ruta, cuerpo, headers=None, timeout=300):
    req = urllib.request.Request(_base() + ruta, data=json.dumps(cuerpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raw = json.dumps({"_http_error": e.code, "_body": e.read().decode(errors="replace")[:500]})
    seg = round(time.time() - t0, 1)
    try:
        return json.loads(raw), seg
    except json.JSONDecodeError:
        return {"respuesta": raw}, seg


def enviar_mensaje(session_id: str, texto: str):
    """Envía un mensaje como cliente. Devuelve (respuesta_texto, segundos)."""
    data, seg = _post("/chat", {"session_id": session_id, "mensaje": texto})
    if "_http_error" in data:
        return f"[ERROR HTTP {data['_http_error']}] {data['_body']}", seg
    prefijo = "[FALLO TÉCNICO] " if data.get("tipo") == "error" else ""
    return prefijo + str(data.get("respuesta", "")), seg


def utilidad(accion: str, **params):
    """Llama a la utilidad de pruebas del API (POST /api/pruebas)."""
    data, _ = _post("/pruebas", {"accion": accion, **params}, {"X-Test-Token": os.environ.get("TEST_TOKEN", "")})
    return data
