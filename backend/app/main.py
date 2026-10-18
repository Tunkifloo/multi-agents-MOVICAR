"""API de MOVICAR (FastAPI).

Canal del cliente (reemplaza el Chat Trigger de n8n / WhatsApp):
  POST /api/conversaciones                 nueva conversación (session_id)
  GET  /api/conversaciones                 historial de conversaciones
  GET  /api/conversaciones/{sid}/mensajes  mensajes de una conversación
  GET  /api/conversaciones/{sid}/solicitud estado de la solicitud de esa conversación
  POST /api/chat/{sid}/stream              turno del asistente en streaming (SSE: pasos + respuesta)
  POST /api/chat                           turno del asistente sin streaming (scripts y pruebas)
Personal del taller (Basic Auth):
  GET  /api/jefe/pendientes · POST /api/jefe/decision · GET /api/jefe/metricas
  GET  /api/solicitudes[/{clave}] · /api/agenda · /api/catalogo · /api/fallos · POST /api/programados/ejecutar
Pruebas (solo con MODO_PRUEBAS=true y cabecera X-Test-Token):
  POST /api/pruebas  {accion: get_solicitud|aprobar_jefe|ocupar_turno|envejecer|contar|listar|correr_programados|reset}
"""
from __future__ import annotations

import json
import logging
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from sqlalchemy import delete, desc, select, update

from . import db
from .asistente import asistente
from .config import a_utc, reglas, settings
from .servicios import agenda, cotizacion, fallos, jefe, programados, solicitudes


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    db.inicializar()
    await asistente.iniciar()
    yield
    await asistente.cerrar()


app = FastAPI(title="MOVICAR · Asistente multiagente", version="3.0", lifespan=ciclo_de_vida)
app.add_middleware(CORSMiddleware, allow_origins=settings().cors_origenes.split(","), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
basic = HTTPBasic(auto_error=False)


def personal(cred: HTTPBasicCredentials | None = Depends(basic)) -> str:
    s = settings()
    if not s.jefe_clave or not cred or not (secrets.compare_digest(cred.username, s.jefe_usuario)
                        and secrets.compare_digest(cred.password, s.jefe_clave)):
        raise HTTPException(401, "Credenciales del personal del taller requeridas",
                            headers={"WWW-Authenticate": 'Basic realm="MOVICAR"'})
    return cred.username


# ------------------------------------------------------------------------- canal cliente ---
class Mensaje(BaseModel):
    mensaje: str = Field(min_length=1, max_length=2000)


class MensajeConSesion(Mensaje):
    session_id: str = Field(min_length=3, max_length=80)


@app.get("/api/salud")
def salud() -> dict:
    s = settings()
    return {"ok": True, "modelo_orquestador": s.modelo_orquestador, "modelo_subagentes": s.modelo_subagentes,
            "bd": "postgresql" if s.url_bd.startswith("postgresql") else "sqlite", "modo_pruebas": s.modo_pruebas,
            "umbral_confianza": reglas()["UMBRAL_CONFIANZA"]}


@app.post("/api/conversaciones")
def crear_conversacion() -> dict:
    return asistente.nueva_conversacion()


@app.get("/api/conversaciones")
def listar_conversaciones() -> list[dict]:
    return asistente.listar_conversaciones()


@app.get("/api/conversaciones/{sid}/mensajes")
def mensajes(sid: str) -> list[dict]:
    return asistente.mensajes_de(sid)


@app.get("/api/conversaciones/{sid}/solicitud")
def solicitud_de_conversacion(sid: str) -> dict:
    filas = solicitudes.de_sesion(sid)
    if not filas:
        return {"existe": False}
    return {"existe": True, **solicitudes.consultar(filas[0]["clave"], sid)["solicitud"]}


@app.post("/api/chat/{sid}/stream")
async def chat_stream(sid: str, cuerpo: Mensaje):
    async def eventos():
        async for ev in asistente.responder(sid, cuerpo.mensaje):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "data: {\"tipo\": \"fin\"}\n\n"
    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/chat")
async def chat(cuerpo: MensajeConSesion) -> dict:
    return await asistente.responder_completo(cuerpo.session_id, cuerpo.mensaje)


# ------------------------------------------------------------------------- jefe de taller --
class Decision(BaseModel):
    clave: str
    decision: Literal["aprobar", "rechazar"]
    tipo_servicio: Literal["preventivo", "correctivo"] | None = None
    prioridad: Literal["normal", "alta"] | None = None
    especialidad: Literal["general", "motor_electrico", "frenos_suspension"] | None = None
    observacion: str = ""


@app.get("/api/jefe/pendientes")
def jefe_pendientes(_: str = Depends(personal)) -> list[dict]:
    return jefe.pendientes()


@app.post("/api/jefe/decision")
def jefe_decision(d: Decision, _: str = Depends(personal)) -> dict:
    return jefe.decidir(d.clave, d.decision, d.tipo_servicio, d.prioridad, d.especialidad, d.observacion)


@app.get("/api/jefe/metricas")
def jefe_metricas(_: str = Depends(personal)) -> dict:
    return jefe.metricas_acuerdo()


@app.get("/api/auth/verificar")
def verificar(usuario: str = Depends(personal)) -> dict:
    return {"ok": True, "usuario": usuario}


# ------------------------------------------------------------------------- back-office -----
def _serializar(f: dict) -> dict:
    out = dict(f)
    for k in ("cotizacion_detalle", "turnos_propuestos", "turno_confirmado"):
        out[k] = json.loads(f[k]) if f.get(k) else None
    return out


@app.get("/api/solicitudes")
def listar_solicitudes(estado: str | None = None, _: str = Depends(personal)) -> list[dict]:
    q = select(db.solicitudes).order_by(desc(db.solicitudes.c.ts_estado)).limit(300)
    if estado:
        q = q.where(db.solicitudes.c.estado == estado)
    with db.engine().connect() as c:
        return [_serializar(db.fila_a_dict(r)) for r in c.execute(q)]


@app.get("/api/solicitudes/{clave}")
def ver_solicitud(clave: str, _: str = Depends(personal)) -> dict:
    with db.engine().connect() as c:
        f = solicitudes.leer(c, clave)
        if not f:
            raise HTTPException(404, "No existe")
        hist = [db.fila_a_dict(r) for r in c.execute(select(db.historial).where(db.historial.c.clave == clave)
                                                      .order_by(db.historial.c.id))]
    return {**_serializar(f), "historial": hist}


@app.get("/api/resumen")
def resumen(_: str = Depends(personal)) -> dict:
    with db.engine().connect() as c:
        filas = [r.estado for r in c.execute(select(db.solicitudes.c.estado))]
        n_fallos = len(c.execute(select(db.cola_fallidos.c.id)).all())
    conteo: dict[str, int] = {}
    for e in filas:
        conteo[e] = conteo.get(e, 0) + 1
    return {"por_estado": conteo, "total": len(filas), "fallos": n_fallos,
            "pendientes_jefe": conteo.get("revision_jefe", 0) + conteo.get("escalada_recepcion", 0)}


@app.get("/api/agenda")
def ver_agenda(desde: str | None = None, dias: int = 7, _: str = Depends(personal)) -> list[dict]:
    return agenda.ver_agenda(desde, min(max(dias, 1), 31))


@app.get("/api/catalogo")
def ver_catalogo(_: str = Depends(personal)) -> list[dict]:
    return cotizacion.catalogo_completo()


@app.get("/api/fallos")
def ver_fallos(_: str = Depends(personal)) -> list[dict]:
    return fallos.listar()


@app.post("/api/programados/ejecutar")
def ejecutar_programados(_: str = Depends(personal)) -> dict:
    return programados.correr_todos()


# ------------------------------------------------------------------------- pruebas ---------
def token_pruebas(x_test_token: str = Header(default="")) -> None:
    s = settings()
    if not s.modo_pruebas or not s.test_token or not secrets.compare_digest(x_test_token, s.test_token):
        raise HTTPException(404, "No encontrado")


@app.post("/api/pruebas", dependencies=[Depends(token_pruebas)])
def pruebas(cuerpo: dict[str, Any]) -> Any:
    """Utilidad de pruebas (equivale a «MOVICAR · Utilidad de pruebas» de la arquitectura v3)."""
    accion = cuerpo.get("accion")
    if accion == "get_solicitud":
        filas = solicitudes.de_sesion(cuerpo.get("session_id", ""))
        return filas[0] if filas else {}
    if accion == "contar":
        return {"n": len(solicitudes.de_sesion(cuerpo.get("session_id", "")))}
    if accion == "aprobar_jefe":
        return jefe.decidir(cuerpo.get("clave", ""), "aprobar", cuerpo.get("tipo_servicio"), cuerpo.get("prioridad"),
                            cuerpo.get("especialidad"), cuerpo.get("observacion", ""), actor="jefe_taller")
    if accion == "ocupar_turno":
        with db.engine().begin() as c:
            r = c.execute(update(db.agenda).where(db.agenda.c.turno_id == cuerpo.get("turno_id"))
                          .values(estado="reservado", clave_solicitud="TEST-OCUPADO"))
        return {"ok": r.rowcount == 1}
    if accion == "envejecer":
        with db.engine().begin() as c:
            ts = c.execute(select(db.solicitudes.c.ts_estado).where(db.solicitudes.c.clave == cuerpo.get("clave"))).scalar()
            if ts is None:
                return {"ok": False}
            c.execute(update(db.solicitudes).where(db.solicitudes.c.clave == cuerpo.get("clave"))
                      .values(ts_estado=a_utc(ts) - timedelta(hours=float(cuerpo.get("horas", 0)))))
        return {"ok": True}
    if accion == "listar":
        with db.engine().connect() as c:
            return {"filas": [db.fila_a_dict(r) for r in c.execute(select(db.solicitudes))]}
    if accion == "correr_programados":
        return programados.correr_todos()
    if accion == "reset":
        with db.engine().begin() as c:
            claves = [r.clave for r in c.execute(select(db.solicitudes.c.clave)
                                                 .where(db.solicitudes.c.telefono.like("+5190000%")))]
            c.execute(update(db.agenda).where(db.agenda.c.clave_solicitud.in_(claves + ["TEST-OCUPADO"]))
                      .values(estado="libre", clave_solicitud=None))
            c.execute(delete(db.historial).where(db.historial.c.clave.in_(claves)))
            c.execute(delete(db.solicitudes).where(db.solicitudes.c.clave.in_(claves)))
        return {"ok": True, "borradas": len(claves)}
    raise HTTPException(400, f"Acción desconocida: {accion}")
