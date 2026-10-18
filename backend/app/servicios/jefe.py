"""Humano en el bucle: pendientes y bandeja del jefe de taller (decisión por CLAVE, no por placa)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select

from ..config import a_utc, ahora_utc, reglas
from ..db import engine, fila_a_dict, solicitudes
from .estados import TransicionInvalida, cambiar_estado
from .solicitudes import ESPECIALIDADES, leer

ESTADOS_PENDIENTES = ("revision_jefe", "escalada_recepcion")


def pendientes() -> list[dict[str, Any]]:
    sla_h = float(reglas()["SLA_REVISION_HORAS"])
    with engine().connect() as c:
        filas = c.execute(select(solicitudes).where(solicitudes.c.estado.in_(ESTADOS_PENDIENTES))
                          .order_by(solicitudes.c.ts_estado)).all()
    ahora = ahora_utc()
    out = []
    for r in filas:
        f = fila_a_dict(r)
        horas = (ahora - a_utc(r.ts_estado)).total_seconds() / 3600
        out.append({**{k: f[k] for k in ("clave", "estado", "telefono", "placa", "vehiculo", "kilometraje",
                                         "descripcion_falla", "fecha_deseada", "tipo_servicio_agente",
                                         "confianza_agente", "prioridad", "especialidad", "motivo_revision",
                                         "creado_en", "ts_estado")},
                    "horas_en_estado": round(horas, 2), "sla_vencido": horas >= sla_h})
    return out


def decidir(clave: str, decision: str, tipo_servicio: str | None = None, prioridad: str | None = None,
            especialidad: str | None = None, observacion: str = "", actor: str = "jefe_taller") -> dict[str, Any]:
    if decision not in ("aprobar", "rechazar"):
        return {"ok": False, "error": "decision_invalida", "mensaje": "La decisión debe ser aprobar o rechazar."}
    observacion = (observacion or "").strip()
    with engine().begin() as c:
        f = leer(c, clave)
        if not f:
            return {"ok": False, "error": "no_encontrada", "mensaje": f"No existe la solicitud {clave}."}
        if f["estado"] not in ESTADOS_PENDIENTES:
            return {"ok": False, "error": "no_pendiente", "estado_actual": f["estado"],
                    "mensaje": f"La solicitud está en estado {f['estado']}; no espera decisión del jefe."}
        try:
            if decision == "rechazar":
                cambiar_estado(c, f, "rechazada", actor, campos={"observacion_jefe": observacion or None,
                                                                 "decidido_por": actor},
                               detalle={"decision": "rechazar", "observacion": observacion})
                return {"ok": True, "estado": "rechazada"}
            if not observacion:
                return {"ok": False, "error": "observacion_requerida",
                        "mensaje": "Para aprobar, escriba la indicación técnica (qué se debe hacer)."}
            tipo = tipo_servicio if tipo_servicio in ("preventivo", "correctivo") else f["tipo_servicio"]
            esp = especialidad if especialidad in ESPECIALIDADES else f["especialidad"]
            prio = prioridad if prioridad in ("normal", "alta") else f["prioridad"]
            cambiar_estado(c, f, "validada_jefe", actor,
                           campos={"tipo_servicio_jefe": tipo, "tipo_servicio": tipo, "especialidad": esp,
                                   "prioridad": prio, "observacion_jefe": observacion, "decidido_por": actor},
                           detalle={"decision": "aprobar", "tipo": tipo, "especialidad": esp, "prioridad": prio})
        except TransicionInvalida as e:
            return {"ok": False, "error": "transicion_invalida", "estado_actual": e.actual}
    return {"ok": True, "estado": "validada_jefe", "clave": clave}


def metricas_acuerdo() -> dict[str, Any]:
    """Bucle de calibración (Arquitectura-futuro): acuerdo agente vs. jefe en el tipo de servicio."""
    with engine().connect() as c:
        filas = [fila_a_dict(r) for r in c.execute(
            select(solicitudes).where(solicitudes.c.tipo_servicio_jefe.is_not(None))
            .order_by(desc(solicitudes.c.ts_estado))).all()]
    n = len(filas)
    acuerdos = sum(f["tipo_servicio_agente"] == f["tipo_servicio_jefe"] for f in filas)
    return {
        "casos_decididos": n, "acuerdos": acuerdos,
        "acuerdo": round(acuerdos / n, 4) if n else None,
        "aprueba_puerta": n >= 30 and acuerdos / n >= 0.9 if n else False,
        "desacuerdos": [{k: f[k] for k in ("clave", "tipo_servicio_agente", "confianza_agente",
                                           "tipo_servicio_jefe", "descripcion_falla")}
                        for f in filas if f["tipo_servicio_agente"] != f["tipo_servicio_jefe"]],
    }
