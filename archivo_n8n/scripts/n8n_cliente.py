"""Cliente HTTP mínimo para el chat de n8n y la utilidad de pruebas (solo biblioteca estándar)."""
import json, os, time, urllib.request, urllib.error
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

def cargar_env():
    env = RAIZ / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            if "=" in linea and not linea.strip().startswith("#"):
                k, v = linea.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def _post(url, cuerpo, headers=None, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode(), method="POST",
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
        return {"output": raw}, seg

def enviar_mensaje(session_id: str, texto: str):
    """Envía un mensaje como cliente. Devuelve (respuesta_texto, segundos)."""
    data, seg = _post(os.environ["N8N_CHAT_URL"], {"action": "sendMessage", "sessionId": session_id, "chatInput": texto})
    if isinstance(data, list) and data:
        data = data[0]
    if "_http_error" in data:
        return f"[ERROR HTTP {data['_http_error']}] {data['_body']}", seg
    return str(data.get("output") or data.get("text") or data.get("response") or data), seg

def utilidad(accion: str, **params):
    """Llama al flujo «MOVICAR · Utilidad de pruebas»."""
    url = os.environ.get("N8N_TEST_URL")
    if not url:
        raise RuntimeError("Falta N8N_TEST_URL en .env (webhook de la utilidad de pruebas)")
    data, _ = _post(url, {"accion": accion, **params}, {"X-Test-Token": os.environ.get("N8N_TEST_TOKEN", "")})
    if isinstance(data, list) and data:
        data = data[0]
    return data
