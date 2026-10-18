"""sw_proponer_turnos · sw_reservar_turno.

- La especialidad del turno se toma de la solicitud registrada (no de la IA).
- Solo se puede reservar un turno que se haya propuesto a ESA solicitud.
- La reserva es atómica (UPDATE ... WHERE estado='libre') e idempotente (defecto 5 de la v2).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, select, update

from ..config import DIAS_SEMANA, TZ, fecha_larga, hoy_lima, reglas
from ..db import agenda, engine
from .estados import TransicionInvalida, cambiar_estado
from .solicitudes import leer


def _opcion(n: int, t) -> dict[str, Any]:
    d = date.fromisoformat(t.fecha)
    return {"opcion": n, "turno_id": t.turno_id, "fecha": t.fecha, "dia_semana": DIAS_SEMANA[d.weekday()],
            "hora": t.hora, "mecanico": t.mecanico}


def texto_turnos(opciones: list[dict]) -> str:
    return "\n".join(
        f"{o['opcion']}. {fecha_larga(date.fromisoformat(o['fecha'])).capitalize()}, {o['hora']} · {o['mecanico']}"
        for o in opciones)


def _normalizar_desde(fecha_desde: str | None, por_defecto: str) -> date:
    hoy = hoy_lima()
    try:
        d = date.fromisoformat((fecha_desde or por_defecto)[:10])
    except ValueError:
        d = date.fromisoformat(por_defecto)
    if d < hoy:
        d = hoy
    if d.weekday() == 6:
        d += timedelta(days=1)
    return d


def proponer(clave: str, session_id: str, fecha_desde: str | None = None, franja: str = "cualquiera") -> dict[str, Any]:
    franja = franja if franja in ("manana", "tarde", "cualquiera") else "cualquiera"
    with engine().begin() as c:
        f = leer(c, clave)
        if not f or f["session_id"] != session_id:
            return {"ok": False, "error": "no_encontrada", "mensaje": "No existe una solicitud de esta sesión con esa clave."}
        if f["estado"] not in reglas()["estados_reservables"]:
            return {"ok": False, "error": "estado_no_reservable", "estado_actual": f["estado"],
                    "mensaje": "Primero debe existir una cotización para proponer turnos."}
        desde = _normalizar_desde(fecha_desde, f["fecha_deseada"])
        ahora = datetime.now(TZ)
        libres = c.execute(select(agenda).where(and_(
            agenda.c.especialidad == f["especialidad"], agenda.c.estado == "libre",
            agenda.c.fecha >= desde.isoformat()))
            .order_by(agenda.c.fecha, agenda.c.hora)).all()
        # descartar los turnos de hoy que ya pasaron
        libres = [t for t in libres
                  if not (t.fecha == ahora.date().isoformat() and t.hora <= ahora.strftime("%H:%M"))]
        elegidos = [t for t in libres if franja == "cualquiera" or t.franja == franja][:3]
        relajada = False
        if len(elegidos) < 3 and franja != "cualquiera":
            relajada = True
            elegidos += [t for t in libres if t not in elegidos][: 3 - len(elegidos)]
        if not elegidos:
            return {"ok": False, "error": "sin_turnos", "mensaje": "No hay turnos libres para esa especialidad en las próximas semanas."}
        opciones = [_opcion(i, t) for i, t in enumerate(elegidos, 1)]
        try:
            cambiar_estado(c, f, f["estado"] if f["estado"] == "cotizada" else "cotizada", "sw_proponer_turnos",
                           campos={"turnos_propuestos": json.dumps(opciones, ensure_ascii=False)},
                           detalle={"desde": desde.isoformat(), "franja": franja,
                                    "turnos": [o["turno_id"] for o in opciones]})
        except TransicionInvalida as e:
            return {"ok": False, "error": "transicion_invalida", "estado_actual": e.actual}
    return {"ok": True, "especialidad": f["especialidad"], "desde": desde.isoformat(), "franja": franja,
            "franja_relajada": relajada, "opciones": opciones, "texto_cliente": texto_turnos(opciones)}


def reservar(clave: str, session_id: str, turno_id: str | None = None, opcion: int | None = None) -> dict[str, Any]:
    r = _reservar(clave, session_id, turno_id, opcion)
    if r.get("error") == "turno_ocupado":
        # «Proponer nuevos turnos» (BPMN) sin otra vuelta por el modelo: desde la misma fecha.
        r["alternativas"] = proponer(clave, session_id, r.pop("_fecha"), "cualquiera")
    return r


def _reservar(clave: str, session_id: str, turno_id: str | None, opcion: int | None) -> dict[str, Any]:
    with engine().begin() as c:
        f = leer(c, clave)
        if not f or f["session_id"] != session_id:
            return {"ok": False, "error": "no_encontrada", "mensaje": "No existe una solicitud de esta sesión con esa clave."}
        propuestos = json.loads(f["turnos_propuestos"]) if f.get("turnos_propuestos") else []
        elegido = None
        if opcion is not None:
            elegido = next((o for o in propuestos if int(o["opcion"]) == int(opcion)), None)
        if elegido is None and turno_id:
            elegido = next((o for o in propuestos if o["turno_id"] == turno_id), None)

        # Idempotencia: si ya está agendada con ese mismo turno, es un éxito.
        if f["estado"] == "agendada":
            conf = json.loads(f["turno_confirmado"]) if f.get("turno_confirmado") else {}
            if elegido and conf.get("turno_id") == elegido["turno_id"] or (turno_id and conf.get("turno_id") == turno_id):
                return {"ok": True, "ya_reservado": True, "turno": conf}
            return {"ok": False, "error": "ya_agendada", "turno": conf,
                    "mensaje": "La solicitud ya tiene una cita confirmada."}
        if f["estado"] not in reglas()["estados_reservables"]:
            return {"ok": False, "error": "estado_no_reservable", "estado_actual": f["estado"]}
        if elegido is None:
            return {"ok": False, "error": "turno_no_propuesto",
                    "mensaje": "Ese turno no está entre las opciones propuestas a esta solicitud."}

        r = c.execute(update(agenda)
                      .where(and_(agenda.c.turno_id == elegido["turno_id"], agenda.c.estado == "libre"))
                      .values(estado="reservado", clave_solicitud=clave))
        if r.rowcount == 0:
            t = c.execute(select(agenda).where(agenda.c.turno_id == elegido["turno_id"])).first()
            if not (t and t.clave_solicitud == clave):
                return {"ok": False, "error": "turno_ocupado", "_fecha": elegido["fecha"],
                        "mensaje": "Ese turno acaba de ser tomado por otro cliente."}
        turno = {k: elegido[k] for k in ("turno_id", "fecha", "dia_semana", "hora", "mecanico")}
        cambiar_estado(c, f, "agendada", "sw_reservar_turno",
                       campos={"turno_confirmado": json.dumps(turno, ensure_ascii=False)}, detalle=turno)
    return {"ok": True, "turno": turno,
            "texto_cliente": f"{fecha_larga(date.fromisoformat(turno['fecha'])).capitalize()}, "
                             f"{turno['hora']} · {turno['mecanico']}"}


def ver_agenda(desde: str | None = None, dias: int = 7) -> list[dict[str, Any]]:
    inicio = date.fromisoformat(desde) if desde else hoy_lima()
    fin = inicio + timedelta(days=dias)
    with engine().connect() as c:
        filas = c.execute(select(agenda).where(and_(agenda.c.fecha >= inicio.isoformat(),
                                                    agenda.c.fecha < fin.isoformat()))
                          .order_by(agenda.c.fecha, agenda.c.hora, agenda.c.mecanico)).all()
    return [dict(f._mapping) for f in filas]
