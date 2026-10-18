"""Registro de fallos (Error Trigger de n8n → manejador de errores del API).

Clasifica el error y lo registra en cola_fallidos con los 6 campos del Lab 02 (+ id).
Defecto 10 de la v2: lo desconocido se clasificaba como de_datos; ahora va a de_sistema.
"""
from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import desc, insert, select

from ..config import ahora_utc
from ..db import cola_fallidos, engine, fila_a_dict

_TRANSITORIO = re.compile(r"timeout|timed out|ETIMEDOUT|ECONNRESET|503|502|504|429|rate|overloaded|unavailable|"
                          r"resource.?exhausted|deadline|temporar|connection (reset|aborted)", re.I)
_DATOS = re.compile(r"validation|invalid argument|json|schema|parse|unprocessable|422", re.I)


def clasificar(error: BaseException | str) -> str:
    msg = f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error)
    if _TRANSITORIO.search(msg):
        return "transitorio"
    if _DATOS.search(msg):
        return "de_datos"
    return "de_sistema"  # credenciales, cuota, modelo inexistente, desconocido


def registrar(flujo: str, ejecucion: str, error: BaseException | str, carga: dict[str, Any], intentos: int) -> dict:
    fila = {
        "momento": ahora_utc(), "flujo": flujo, "ejecucion": ejecucion, "clase_error": clasificar(error),
        "motivo": (f"{type(error).__name__}: {error}" if isinstance(error, BaseException) else str(error))[:2000],
        "carga_original": json.dumps(carga, ensure_ascii=False, default=str)[:4000], "intentos": intentos,
    }
    with engine().begin() as c:
        c.execute(insert(cola_fallidos).values(**fila))
    return fila


def listar(limite: int = 100) -> list[dict]:
    with engine().connect() as c:
        return [fila_a_dict(r) for r in c.execute(select(cola_fallidos).order_by(desc(cola_fallidos.c.id)).limit(limite)).all()]
