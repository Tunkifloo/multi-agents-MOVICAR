"""Contrato de entrada (Lab 02, v3) y clave de idempotencia.

Port 1:1 de scripts/lib/contrato.js (elemento protegido, fuente de la especificación).
tests/test_contrato.py verifica la paridad ejecutando el .js con Node: misma entrada → misma clave.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from .config import TZ, reglas

_U32 = 0xFFFFFFFF


def _imul(a: int, b: int) -> int:
    """Math.imul de JavaScript en el espacio uint32 (los bits coinciden)."""
    return ((a & _U32) * (b & _U32)) & _U32


def calcular_clave(tel: str, placa: str, fecha: str) -> str:
    """Clave de negocio: teléfono | placa | fecha. Sin tipo_servicio (lo infiere la IA)."""
    material = "|".join([tel, placa, fecha]).lower()
    h1, h2 = 0xDEADBEEF, 0x41C6CE57
    # charCodeAt → unidades UTF-16
    codigos = material.encode("utf-16-le")
    for i in range(0, len(codigos), 2):
        ch = codigos[i] | (codigos[i + 1] << 8)
        h1 = _imul(h1 ^ ch, 2654435761)
        h2 = _imul(h2 ^ ch, 1597334677)
    h1 = _imul(h1 ^ (h1 >> 16), 2246822507) ^ _imul(h2 ^ (h2 >> 13), 3266489909)
    h2 = _imul(h2 ^ (h2 >> 16), 2246822507) ^ _imul(h1 ^ (h1 >> 13), 3266489909)
    return f"MV-{h2 & _U32:08x}{h1 & _U32:08x}"


def _hoy(ahora: datetime | str | None) -> date:
    if ahora is None:
        return datetime.now(TZ).date()
    if isinstance(ahora, str):
        ahora = datetime.fromisoformat(ahora.replace("Z", "+00:00"))
    return ahora.astimezone(TZ).date()


def validar_contrato(q: dict[str, Any] | None, ahora: datetime | str | None = None) -> dict[str, Any]:
    q = q or {}
    dias_max = int(reglas().get("DIAS_MAX_ANTICIPACION", 60))
    errores: list[str] = []
    hoy = _hoy(ahora)

    # teléfono
    tel = re.sub(r"[\s\-().]", "", str(q.get("telefono") or ""))
    if re.fullmatch(r"9\d{8}", tel):
        tel = "+51" + tel
    elif re.fullmatch(r"51\d{9}", tel):
        tel = "+" + tel
    if not re.fullmatch(r"\+\d{10,15}", tel):
        errores.append("telefono: se necesita un celular válido de 9 dígitos (ej. 987 654 321)")

    # placa (Perú: 6 alfanuméricos)
    placa = re.sub(r"[^A-Z0-9]", "", str(q.get("placa") or "").upper())
    if not re.fullmatch(r"[A-Z0-9]{6}", placa):
        errores.append("placa: debe tener 6 caracteres (ej. ABC-123)")
    else:
        placa = placa[:3] + "-" + placa[3:]

    # vehículo
    vehiculo = str(q.get("vehiculo") or "").strip()
    if len(vehiculo) < 3 or len(vehiculo) > 80:
        errores.append("vehiculo: indique marca, modelo y año")

    # fecha
    fecha = str(q.get("fecha_deseada") or "").strip()[:10]
    f: date | None = None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fecha):
        try:
            f = date.fromisoformat(fecha)
        except ValueError:
            f = None
    if f is None:
        errores.append("fecha_deseada: falta una fecha válida (AAAA-MM-DD)")
    else:
        dias = (f - hoy).days
        if dias < 0:
            errores.append(f"fecha_deseada: no puede ser anterior a hoy ({hoy.isoformat()})")
        elif dias > dias_max:
            errores.append(f"fecha_deseada: solo agendamos hasta {dias_max} días adelante")
        elif f.weekday() == 6:
            errores.append("fecha_deseada: los domingos no atendemos")

    # descripción
    desc = str(q.get("descripcion_falla") or "").strip()
    if not desc:
        errores.append("descripcion_falla: falta el servicio o síntoma")
    elif len(desc) > 500:
        errores.append("descripcion_falla: máximo 500 caracteres")

    # kilometraje
    try:
        km = float(q.get("kilometraje"))
        if km != km or km < 0 or km in (float("inf"),):
            km = 0.0
    except (TypeError, ValueError):
        km = 0.0

    valido = not errores
    return {
        "valido": valido,
        "errores": errores,
        "clave": calcular_clave(tel, placa, fecha) if valido else "",
        "datos": {"telefono": tel, "placa": placa, "vehiculo": vehiculo, "kilometraje": int(round(km)),
                  "fecha_deseada": fecha, "descripcion_falla": desc},
    }
