"""Herramientas de los agentes (LangChain tools con esquemas Pydantic).

Cada herramienta es una envoltura delgada sobre app/servicios (la capa determinista):
- session_id se toma de runtime.context (inyectado por el canal), nunca de los argumentos del modelo;
- ningún argumento permite al modelo fijar estado, precio, stock, total ni especialidad del turno.
"""
from __future__ import annotations

import json
from typing import Annotated, Literal

from langchain.tools import ToolRuntime, tool
from pydantic import BaseModel, Field

from ..contrato import validar_contrato
from ..servicios import agenda, cotizacion, solicitudes
from .base import Contexto


def _json(x) -> str:
    return json.dumps(x, ensure_ascii=False, default=str)


Tel = Annotated[str, Field(description="Celular del cliente, tal como lo escribió")]
Placa = Annotated[str, Field(description="Placa del vehículo, tal como la escribió")]
Vehiculo = Annotated[str, Field(description="Marca, modelo y año")]
Km = Annotated[float, Field(description="Kilometraje; 0 si no lo sabe")]
Fecha = Annotated[str, Field(description="Fecha deseada en formato AAAA-MM-DD")]
Desc = Annotated[str, Field(description="Servicio solicitado o síntoma, con las palabras del cliente")]


# ---------------------------------------------------------------- orquestador -----------
@tool
def validar_solicitud(telefono: Tel, placa: Placa, vehiculo: Vehiculo, fecha_deseada: Fecha,
                      descripcion_falla: Desc, runtime: ToolRuntime[Contexto], kilometraje: Km = 0) -> str:
    """Valida y normaliza los datos del cliente contra el contrato de entrada, calcula la clave de
    idempotencia y consulta si esa clave ya está registrada. Devuelve {valido, errores, clave, datos, consulta}.
    Llámala cuando tengas los cinco datos obligatorios."""
    runtime.context.paso("orquestador", "validar_solicitud", "Validando los datos y buscando si ya existe la solicitud")
    r = validar_contrato({"telefono": telefono, "placa": placa, "vehiculo": vehiculo, "kilometraje": kilometraje,
                          "fecha_deseada": fecha_deseada, "descripcion_falla": descripcion_falla})
    if r["valido"]:
        # «¿Clave ya registrada?» (BPMN) en el mismo paso: una llamada menos al modelo por turno.
        r["consulta"] = solicitudes.consultar(r["clave"], runtime.context.session_id)
    return _json(r)


@tool
def consultar_solicitud(clave: str, runtime: ToolRuntime[Contexto]) -> str:
    """Consulta si la clave ya está registrada y en qué estado. Si pertenece a otra conversación no devuelve datos."""
    runtime.context.paso("orquestador", "consultar_solicitud", "Buscando si la solicitud ya existe")
    return _json(solicitudes.consultar(clave, runtime.context.session_id))


@tool
def mis_solicitudes(runtime: ToolRuntime[Contexto]) -> str:
    """Lista las solicitudes de ESTA conversación (la más reciente primero) con su estado actual.
    Úsala cuando el cliente pregunte por el estado, su cita o su cotización."""
    runtime.context.paso("orquestador", "mis_solicitudes", "Revisando el estado de tu solicitud")
    filas = solicitudes.de_sesion(runtime.context.session_id)
    return _json([solicitudes.consultar(f["clave"], runtime.context.session_id)["solicitud"] for f in filas[:3]])


@tool
def registrar_solicitud(
    telefono: Tel, placa: Placa, vehiculo: Vehiculo, fecha_deseada: Fecha, descripcion_falla: Desc,
    tipo_servicio_agente: Annotated[Literal["preventivo", "correctivo"], Field(description="Tu clasificación")],
    confianza_agente: Annotated[float, Field(description="Tu confianza en la clasificación, de 0 a 1")],
    prioridad_sugerida: Annotated[Literal["normal", "alta"], Field(description="alta si hay riesgo de seguridad")],
    especialidad_sugerida: Literal["general", "motor_electrico", "frenos_suspension"],
    runtime: ToolRuntime[Contexto], kilometraje: Km = 0,
) -> str:
    """Registra la solicitud. El estado inicial lo decide la herramienta (compuerta de riesgo):
    correctivo o confianza baja → revision_jefe; si no → lista_para_cotizar."""
    runtime.context.paso("orquestador", "registrar_solicitud", "Registrando la solicitud y aplicando la compuerta de riesgo")
    datos = {"telefono": telefono, "placa": placa, "vehiculo": vehiculo, "kilometraje": kilometraje,
             "fecha_deseada": fecha_deseada, "descripcion_falla": descripcion_falla}
    return _json(solicitudes.registrar(datos, tipo_servicio_agente, confianza_agente, prioridad_sugerida,
                                       especialidad_sugerida, runtime.context.session_id))


@tool
def rechazar_solicitud(clave: str, runtime: ToolRuntime[Contexto]) -> str:
    """Cierra la solicitud porque el cliente no desea continuar."""
    runtime.context.paso("orquestador", "rechazar_solicitud", "Cerrando la solicitud")
    return _json(solicitudes.rechazar(clave, runtime.context.session_id))


# ---------------------------------------------------------------- cotizador -------------
@tool
def consultar_catalogo(runtime: ToolRuntime[Contexto]) -> str:
    """Devuelve el catálogo de servicios y repuestos (código, concepto, tipo, categoría, especialidad y
    aplica_a). No incluye precios: los aplica la herramienta cotizar."""
    runtime.context.paso("cotizador", "consultar_catalogo", "Leyendo el catálogo de servicios")
    return _json(cotizacion.catalogo_para_agente())


class Item(BaseModel):
    codigo: str = Field(description="Código exacto del catálogo, p. ej. MO-PREV-10K")
    cantidad: int = Field(1, ge=1, le=10)


@tool(return_direct=True)
def cotizar(clave: str, items: list[Item], runtime: ToolRuntime[Contexto]) -> str:
    """Calcula y guarda la cotización con los precios y el stock del tarifario. Recibe solo códigos y cantidades."""
    runtime.context.paso("cotizador", "cotizar", "Calculando la cotización con el tarifario")
    lista = [i.model_dump() if isinstance(i, BaseModel) else dict(i) for i in items]
    return _json(cotizacion.cotizar(clave, lista, runtime.context.session_id))


# ---------------------------------------------------------------- agenda ----------------
@tool(return_direct=True)
def proponer_turnos(clave: str, fecha_desde: str, franja: Literal["manana", "tarde", "cualquiera"],
                    runtime: ToolRuntime[Contexto]) -> str:
    """Propone 3 turnos libres desde fecha_desde (AAAA-MM-DD) en la franja indicada. La especialidad la
    toma de la solicitud registrada. Guarda las opciones numeradas 1, 2 y 3."""
    runtime.context.paso("agenda", "proponer_turnos", f"Buscando turnos libres desde {fecha_desde} ({franja})")
    return _json(agenda.proponer(clave, runtime.context.session_id, fecha_desde, franja))


@tool(return_direct=True)
def reservar_turno(clave: str, runtime: ToolRuntime[Contexto], opcion: int | None = None,
                   turno_id: str | None = None) -> str:
    """Reserva uno de los turnos propuestos a esta solicitud, por número de opción (1, 2 o 3) o por turno_id.
    Si el turno ya fue tomado, devuelve alternativas desde la misma fecha."""
    runtime.context.paso("agenda", "reservar_turno", "Reservando el turno elegido")
    return _json(agenda.reservar(clave, runtime.context.session_id, turno_id=turno_id, opcion=opcion))
