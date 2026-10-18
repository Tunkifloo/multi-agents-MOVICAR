"""Flujos programados (Schedule Trigger de n8n → APScheduler en el servicio «worker»).

- SLA de revisión: revision_jefe con más de SLA_REVISION_HORAS → escalada_recepcion.
- Seguimiento: cotizada sin respuesta por SEGUIMIENTO_HORAS → sin_confirmar_seguimiento.
Se usa ts_estado (no la fecha de última modificación, que cambia con cualquier escritura).
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import and_, select

from ..config import ahora_utc, reglas
from ..db import asegurar_agenda, engine, fila_a_dict, solicitudes
from .estados import cambiar_estado


def _vencidas(estado: str, horas: float, nuevo: str, actor: str) -> list[str]:
    limite = ahora_utc() - timedelta(hours=horas)
    claves = []
    with engine().begin() as c:
        filas = c.execute(select(solicitudes).where(and_(solicitudes.c.estado == estado,
                                                         solicitudes.c.ts_estado < limite))).all()
        for r in filas:
            cambiar_estado(c, fila_a_dict(r), nuevo, actor, detalle={"plazo_horas": horas})
            claves.append(r.clave)
    return claves


def vencer_sla_revision() -> list[str]:
    return _vencidas("revision_jefe", float(reglas()["SLA_REVISION_HORAS"]), "escalada_recepcion", "sla_revision_2h")


def seguimiento_48h() -> list[str]:
    return _vencidas("cotizada", float(reglas()["SEGUIMIENTO_HORAS"]), "sin_confirmar_seguimiento", "seguimiento_48h")


def correr_todos() -> dict:
    return {"escaladas": vencer_sla_revision(), "seguimiento": seguimiento_48h(), "turnos_creados": asegurar_agenda()}
