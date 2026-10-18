"""Máquina de estados de una solicitud (config/reglas.json → transiciones) y trazas."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import insert, update
from sqlalchemy.engine import Connection

from ..config import ahora_utc, reglas
from ..db import historial, solicitudes


class TransicionInvalida(Exception):
    def __init__(self, actual: str, nuevo: str):
        super().__init__(f"{actual} → {nuevo} no permitido")
        self.actual, self.nuevo = actual, nuevo


def transicion_permitida(actual: str | None, nuevo: str) -> bool:
    if actual is None:
        return nuevo in reglas()["transiciones"]["nueva"]
    return nuevo in reglas()["transiciones"].get(actual, [])


def cambiar_estado(c: Connection, fila: dict[str, Any], nuevo: str, actor: str,
                   campos: dict[str, Any] | None = None, detalle: Any = None) -> dict[str, Any]:
    """Aplica una transición validada; escribe la fila y deja la traza en historial_estados.

    Si la transición no está en reglas.json lanza TransicionInvalida (el llamador la convierte en
    {ok:false, error:'transicion_invalida'}: es un error de negocio, no técnico).
    """
    actual = fila["estado"]
    if not transicion_permitida(actual, nuevo):
        raise TransicionInvalida(actual, nuevo)
    ahora = ahora_utc()
    valores = dict(campos or {})
    valores["estado"] = nuevo
    if nuevo != actual:
        valores["ts_estado"] = ahora
    c.execute(update(solicitudes).where(solicitudes.c.clave == fila["clave"]).values(**valores))
    c.execute(insert(historial).values(
        clave=fila["clave"], estado_anterior=actual, estado_nuevo=nuevo, actor=actor, momento=ahora,
        detalle=json.dumps(detalle, ensure_ascii=False, default=str) if detalle is not None else None))
    return {**fila, **valores}


def registrar_traza_creacion(c: Connection, clave: str, estado: str, actor: str, detalle: Any) -> None:
    c.execute(insert(historial).values(clave=clave, estado_anterior=None, estado_nuevo=estado, actor=actor,
                                       momento=ahora_utc(),
                                       detalle=json.dumps(detalle, ensure_ascii=False, default=str)))
