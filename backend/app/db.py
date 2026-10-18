"""Capa de datos (SQLAlchemy Core). Equivale a las Data Tables de n8n de la v2.

Tablas de negocio (las 4 de la v2, ampliadas según docs/ARQUITECTURA.md §6):
  catalogo_servicios · agenda_turnos · solicitudes · cola_fallidos
Tablas de soporte:
  historial_estados (trazas de cada transición) · conversaciones · mensajes (para la interfaz de chat)

PostgreSQL en Docker; SQLite para desarrollo local y pruebas.
"""
from __future__ import annotations

import csv
from datetime import timedelta

from sqlalchemy import (Boolean, Column, DateTime, Float, Integer, MetaData, String, Table, Text,
                        create_engine, event, func, insert, select)
from sqlalchemy.engine import Engine

from .config import RAIZ, ahora_utc, hoy_lima, settings

metadata = MetaData()

catalogo = Table(
    "catalogo_servicios", metadata,
    Column("codigo", String(30), primary_key=True),
    Column("concepto", String(200), nullable=False),
    Column("tipo", String(20), nullable=False),          # mano_obra | repuesto
    Column("categoria", String(20), nullable=False),     # preventivo | correctivo
    Column("especialidad", String(30), nullable=False),
    Column("precio_unitario", Float, nullable=False),
    Column("stock", Integer, nullable=False, default=0),
    Column("horas", Float, nullable=False, default=0),
    Column("aplica_a", Text, nullable=False, default=""),
)

agenda = Table(
    "agenda_turnos", metadata,
    Column("turno_id", String(30), primary_key=True),
    Column("fecha", String(10), nullable=False, index=True),   # AAAA-MM-DD
    Column("hora", String(5), nullable=False),                 # HH:MM
    Column("franja", String(10), nullable=False),              # manana | tarde
    Column("mecanico", String(40), nullable=False),
    Column("especialidad", String(30), nullable=False, index=True),
    Column("estado", String(12), nullable=False, default="libre"),
    Column("clave_solicitud", String(40), nullable=True),
)

solicitudes = Table(
    "solicitudes", metadata,
    Column("clave", String(40), primary_key=True),
    Column("session_id", String(80), nullable=False, index=True),
    Column("telefono", String(20), nullable=False),
    Column("placa", String(10), nullable=False),
    Column("vehiculo", String(80), nullable=False),
    Column("kilometraje", Integer, nullable=False, default=0),
    Column("descripcion_falla", Text, nullable=False),
    Column("fecha_deseada", String(10), nullable=False),
    Column("tipo_servicio_agente", String(12), nullable=False),
    Column("confianza_agente", Float, nullable=False),
    Column("tipo_servicio", String(12), nullable=False),
    Column("prioridad", String(10), nullable=False),
    Column("especialidad", String(30), nullable=False),
    Column("motivo_revision", Text, nullable=True),
    Column("tipo_servicio_jefe", String(12), nullable=True),
    Column("observacion_jefe", Text, nullable=True),
    Column("decidido_por", String(20), nullable=True),
    Column("total_cotizacion", Float, nullable=True),
    Column("cotizacion_detalle", Text, nullable=True),     # JSON
    Column("requiere_proveedor", Boolean, nullable=False, default=False),
    Column("turnos_propuestos", Text, nullable=True),      # JSON (lista de opciones numeradas)
    Column("turno_confirmado", Text, nullable=True),       # JSON
    Column("estado", String(30), nullable=False, index=True),
    Column("creado_en", DateTime(timezone=True), nullable=False),
    Column("ts_estado", DateTime(timezone=True), nullable=False),
)

historial = Table(
    "historial_estados", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("clave", String(40), nullable=False, index=True),
    Column("estado_anterior", String(30), nullable=True),
    Column("estado_nuevo", String(30), nullable=False),
    Column("actor", String(40), nullable=False),           # sw_registrar, jefe_taller, sla_2h, ...
    Column("detalle", Text, nullable=True),
    Column("momento", DateTime(timezone=True), nullable=False),
)

cola_fallidos = Table(
    "cola_fallidos", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("momento", DateTime(timezone=True), nullable=False),
    Column("flujo", String(80), nullable=False),
    Column("ejecucion", String(80), nullable=False),
    Column("clase_error", String(20), nullable=False),     # transitorio | de_datos | de_sistema
    Column("motivo", Text, nullable=False),
    Column("carga_original", Text, nullable=False),
    Column("intentos", Integer, nullable=False),
)

conversaciones = Table(
    "conversaciones", metadata,
    Column("session_id", String(80), primary_key=True),
    Column("titulo", String(120), nullable=False),
    Column("creado_en", DateTime(timezone=True), nullable=False),
    Column("actualizado_en", DateTime(timezone=True), nullable=False),
)

mensajes = Table(
    "mensajes", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(80), nullable=False, index=True),
    Column("rol", String(12), nullable=False),             # cliente | asistente | error
    Column("contenido", Text, nullable=False),
    Column("pasos", Text, nullable=True),                  # JSON: herramientas/agentes usados
    Column("segundos", Float, nullable=True),
    Column("creado_en", DateTime(timezone=True), nullable=False),
)

_engine: Engine | None = None

TECNICOS = [("A", "Técnico A", "general"), ("B", "Técnico B", "motor_electrico"),
            ("C", "Técnico C", "frenos_suspension")]
HORAS = ["08:00", "11:00", "15:00"]


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings().url_bd
        if url.startswith("sqlite"):
            _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})

            @event.listens_for(_engine, "connect")
            def _pragma(dbapi_conn, _):  # pragma: no cover - configuración
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.close()
        else:
            _engine = create_engine(url, pool_pre_ping=True)
    return _engine


def reiniciar_engine(url: str | None = None) -> Engine:
    """Para pruebas: apunta a otra base de datos."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
    if url is not None:
        settings().database_url = url
    return engine()


def inicializar(sembrar: bool = True) -> None:
    metadata.create_all(engine())
    if sembrar:
        sembrar_catalogo()
        asegurar_agenda()


def sembrar_catalogo(forzar: bool = False) -> int:
    ruta = RAIZ / settings().catalogo_csv
    with engine().begin() as c:
        if not forzar and c.execute(select(func.count()).select_from(catalogo)).scalar():
            return 0
        if forzar:
            c.execute(catalogo.delete())
        filas = []
        with ruta.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                filas.append({
                    "codigo": r["codigo"].strip(), "concepto": r["concepto"].strip(), "tipo": r["tipo"].strip(),
                    "categoria": r["categoria"].strip(), "especialidad": r["especialidad"].strip(),
                    "precio_unitario": float(r.get("precio_unitario") or r.get("precio") or 0),
                    "stock": int(float(r.get("stock") or 0)), "horas": float(r.get("horas") or 0),
                    "aplica_a": (r.get("aplica_a") or "").strip(),
                })
        c.execute(insert(catalogo), filas)
        return len(filas)


def asegurar_agenda(dias: int | None = None) -> int:
    """Crea los turnos que falten desde hoy (Lima) hasta hoy + N días (lunes a sábado).

    Corrige el defecto 11 de la v2: la agenda ya no caduca, se genera relativa a la fecha de ejecución.
    """
    dias = dias or settings().dias_agenda
    inicio = hoy_lima()
    with engine().begin() as c:
        existentes = set(c.execute(select(agenda.c.turno_id).where(agenda.c.fecha >= inicio.isoformat())).scalars())
        nuevos = []
        for d in range(dias):
            dia = inicio + timedelta(days=d)
            if dia.weekday() == 6:
                continue
            for hora in HORAS:
                for letra, nombre, esp in TECNICOS:
                    tid = f"T-{dia:%y%m%d}-{hora[:2]}-{letra}"
                    if tid in existentes:
                        continue
                    nuevos.append({"turno_id": tid, "fecha": dia.isoformat(), "hora": hora,
                                   "franja": "manana" if int(hora[:2]) < 12 else "tarde",
                                   "mecanico": nombre, "especialidad": esp, "estado": "libre",
                                   "clave_solicitud": None})
        if nuevos:
            c.execute(insert(agenda), nuevos)
        return len(nuevos)


def fila_a_dict(fila) -> dict:
    d = dict(fila._mapping)
    for k, v in list(d.items()):
        if hasattr(v, "isoformat") and k in ("creado_en", "ts_estado", "momento", "actualizado_en"):
            from .config import a_utc
            d[k] = a_utc(v).isoformat()
    return d


__all__ = ["metadata", "catalogo", "agenda", "solicitudes", "historial", "cola_fallidos", "conversaciones",
           "mensajes", "engine", "inicializar", "sembrar_catalogo", "asegurar_agenda", "fila_a_dict",
           "reiniciar_engine", "ahora_utc"]
