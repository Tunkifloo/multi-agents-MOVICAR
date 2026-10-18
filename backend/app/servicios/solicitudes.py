"""sw_consultar_solicitud · sw_registrar_solicitud · sw_rechazar_solicitud.

Regla de diseño: la IA decide QUÉ hacer; este código garantiza CÓMO. El session_id llega siempre
desde el contexto de ejecución (nunca desde el modelo) y el estado lo decide el código.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from sqlalchemy import desc, insert, select

from ..config import ahora_utc, reglas
from ..contrato import validar_contrato
from ..db import engine, fila_a_dict, solicitudes
from .estados import TransicionInvalida, cambiar_estado, registrar_traza_creacion

ESPECIALIDADES = ("general", "motor_electrico", "frenos_suspension")

# Red de seguridad determinista de la compuerta de riesgo: si el texto describe un síntoma,
# la solicitud va al jefe aunque el agente la haya clasificado como preventiva (escenario E10).
SINTOMAS = [
    "ruido", "chirr", "rechin", "vibra", "golpe", "tiembla", "temblor", "se apaga", "apaga", "check engine",
    "luz del tablero", "luz de", "testigo", "falla", "no arranca", "no prende", "patina", "humo", "fuga",
    "gotea", "pierde", "tironea", "jalonea", "cascabel", "huele", "olor", "recalienta", "se calienta",
    "esponjoso", "suena", "sonido", "jala hacia", "se desvia", "no enfria", "descarga", "duro", "chilla",
]


def _normalizar(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn")


def detectar_sintomas(texto: str) -> list[str]:
    t = _normalizar(texto)
    return [s for s in SINTOMAS if re.search(r"\b" + re.escape(s), t)]


def _vista_cliente(f: dict[str, Any]) -> dict[str, Any]:
    """Lo que el orquestador puede ver de su propia solicitud."""
    return {
        "clave": f["clave"], "estado": f["estado"], "vehiculo": f["vehiculo"], "placa": f["placa"],
        "fecha_deseada": f["fecha_deseada"], "kilometraje": f["kilometraje"],
        "descripcion_falla": f["descripcion_falla"], "tipo_servicio": f["tipo_servicio"],
        "prioridad": f["prioridad"], "especialidad": f["especialidad"],
        "observacion_jefe": f.get("observacion_jefe") or "",
        "total_cotizacion": f.get("total_cotizacion"),
        "cotizacion_detalle": json.loads(f["cotizacion_detalle"]) if f.get("cotizacion_detalle") else None,
        "requiere_proveedor": bool(f.get("requiere_proveedor")),
        "turnos_propuestos": json.loads(f["turnos_propuestos"]) if f.get("turnos_propuestos") else None,
        "turno_confirmado": json.loads(f["turno_confirmado"]) if f.get("turno_confirmado") else None,
    }


def leer(c, clave: str) -> dict[str, Any] | None:
    r = c.execute(select(solicitudes).where(solicitudes.c.clave == clave)).first()
    return fila_a_dict(r) if r else None


def consultar(clave: str, session_id: str) -> dict[str, Any]:
    with engine().connect() as c:
        f = leer(c, clave)
    if not f:
        return {"ok": True, "existe": False}
    if f["session_id"] != session_id:
        # Aislamiento por cliente (defecto 4 de la v2): ningún dato de la solicitud ajena.
        return {"ok": True, "existe": True, "misma_sesion": False}
    return {"ok": True, "existe": True, "misma_sesion": True, "solicitud": _vista_cliente(f)}


def de_sesion(session_id: str) -> list[dict[str, Any]]:
    with engine().connect() as c:
        filas = c.execute(select(solicitudes).where(solicitudes.c.session_id == session_id)
                          .order_by(desc(solicitudes.c.creado_en))).all()
    return [fila_a_dict(f) for f in filas]


def registrar(datos: dict[str, Any], tipo_servicio_agente: str, confianza_agente: Any,
              prioridad_sugerida: str, especialidad_sugerida: str, session_id: str) -> dict[str, Any]:
    r = validar_contrato(datos)
    if not r["valido"]:
        return {"ok": False, "error": "contrato", "errores": r["errores"],
                "mensaje": "Los datos no cumplen el contrato de entrada."}
    clave, d = r["clave"], r["datos"]

    tipo = tipo_servicio_agente if tipo_servicio_agente in ("preventivo", "correctivo") else "correctivo"
    try:
        conf = float(confianza_agente)
        if not 0 <= conf <= 1:
            conf = 0.0
    except (TypeError, ValueError):
        conf = 0.0
    prioridad = prioridad_sugerida if prioridad_sugerida in ("normal", "alta") else "normal"
    especialidad = especialidad_sugerida if especialidad_sugerida in ESPECIALIDADES else "general"

    with engine().begin() as c:
        existente = leer(c, clave)
        if existente:
            if existente["session_id"] != session_id:
                return {"ok": True, "ya_existia": True, "misma_sesion": False}
            return {"ok": True, "ya_existia": True, "misma_sesion": True, "clave": clave,
                    "estado": existente["estado"]}

        # Compuerta de riesgo EN CÓDIGO (defecto 3 de la v2: vivía en el prompt).
        umbral = float(reglas()["UMBRAL_CONFIANZA"])
        motivos = []
        if tipo == "correctivo":
            motivos.append("correctivo")
        if conf < umbral:
            motivos.append(f"confianza {conf:.2f} < {umbral:.2f}")
        sintomas = detectar_sintomas(d["descripcion_falla"]) if tipo == "preventivo" else []
        if sintomas:
            motivos.append("síntomas detectados: " + ", ".join(sintomas))
        estado = "revision_jefe" if motivos else "lista_para_cotizar"
        if tipo == "preventivo" and not sintomas:
            especialidad = "general"

        ahora = ahora_utc()
        fila = {
            "clave": clave, "session_id": session_id, **d,
            "tipo_servicio_agente": tipo, "confianza_agente": conf, "tipo_servicio": tipo,
            "prioridad": prioridad, "especialidad": especialidad,
            "motivo_revision": "; ".join(motivos) or None, "requiere_proveedor": False,
            "estado": estado, "creado_en": ahora, "ts_estado": ahora,
        }
        c.execute(insert(solicitudes).values(**fila))
        registrar_traza_creacion(c, clave, estado, "sw_registrar_solicitud",
                                 {"tipo_agente": tipo, "confianza": conf, "motivos": motivos})
    return {"ok": True, "ya_existia": False, "clave": clave, "estado": estado,
            "motivo_revision": "; ".join(motivos) or None}


def rechazar(clave: str, session_id: str, motivo: str = "cliente no desea continuar") -> dict[str, Any]:
    with engine().begin() as c:
        f = leer(c, clave)
        if not f or f["session_id"] != session_id:
            return {"ok": False, "error": "no_encontrada", "mensaje": "No hay una solicitud tuya con esa clave."}
        if f["estado"] == "rechazada":
            return {"ok": True, "estado": "rechazada", "ya_estaba": True}
        try:
            cambiar_estado(c, f, "rechazada", "sw_rechazar_solicitud", detalle={"motivo": motivo})
        except TransicionInvalida as e:
            return {"ok": False, "error": "transicion_invalida", "estado_actual": e.actual,
                    "mensaje": f"La solicitud está en estado {e.actual} y no se puede cerrar desde el chat."}
    return {"ok": True, "estado": "rechazada"}
