"""Patrón supervisor: Agente Orquestador + subagentes-herramienta (Cotizador y Agenda).

Equivalencias con la v2 de n8n:
  AI Agent (orquestador)        → create_agent(...) con checkpointer (memoria por sesión)
  AI Agent Tool (subagentes)    → herramientas async que invocan otro create_agent
  Gemini compartido             → ChatGoogleGenerativeAI + InMemoryRateLimiter compartido
  maxIterations / reintentos    → ModelCallLimitMiddleware / ModelRetryMiddleware

Mejora respecto de la v2: lo que el subagente devuelve al orquestador es el RESULTADO DE LA
HERRAMIENTA determinista (precios, turnos), no una transcripción hecha por el LLM.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Literal

from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ModelFallbackMiddleware, ModelRetryMiddleware
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import HumanMessage, ToolMessage

from ..config import settings
from ..servicios import solicitudes
from . import herramientas as h
from .base import Contexto, PromptYVentana, RegistroLLM, leer_prompt, modelo


def _middleware_comun(agente: str, principal: str, plantilla: str, ventana: int | None, limite: int):
    """Orden = de afuera hacia adentro: prompt/ventana → reintentos con backoff → respaldo de modelo."""
    s = settings()
    mw = [
        PromptYVentana(plantilla, ventana),
        ModelRetryMiddleware(max_retries=s.llm_reintentos, on_failure="error", initial_delay=5.0, max_delay=60.0),
    ]
    respaldos = [modelo(m) for m in s.respaldos if m != principal]
    if respaldos:
        mw.append(ModelFallbackMiddleware(*respaldos))  # 429 / cuota llena → otro modelo, sin esperar
    mw.append(RegistroLLM(agente))
    mw.append(ModelCallLimitMiddleware(run_limit=limite, exit_behavior="end"))
    return mw


@lru_cache
def agente_cotizador_grafo():
    m = settings().modelo_subagentes
    return create_agent(
        modelo(m), [h.consultar_catalogo, h.cotizar],
        middleware=_middleware_comun("cotizador", m, leer_prompt("cotizador"), None, 6),
        context_schema=Contexto, name="agente_cotizador", checkpointer=False,
    )


@lru_cache
def agente_agenda_grafo():
    m = settings().modelo_subagentes
    return create_agent(
        modelo(m), [h.proponer_turnos, h.reservar_turno],
        middleware=_middleware_comun("agenda", m, leer_prompt("agenda"), None, 6),
        context_schema=Contexto, name="agente_agenda", checkpointer=False,
    )


def _resultados(mensajes: list, nombre: str) -> list[dict[str, Any]]:
    out = []
    for m in mensajes:
        if isinstance(m, ToolMessage) and m.name == nombre:
            try:
                out.append(json.loads(m.content if isinstance(m.content, str) else m.text))
            except (json.JSONDecodeError, TypeError):
                out.append({"ok": False, "error": "respuesta_no_json", "crudo": str(m.content)[:300]})
    return out


def _nota(mensajes: list) -> str:
    final = mensajes[-1] if mensajes else None
    return (getattr(final, "text", "") or "").strip()[:500] if final is not None and final.type == "ai" else ""


@tool
async def agente_cotizador(clave: str, pedido: str, runtime: ToolRuntime[Contexto]) -> str:
    """Agente Cotizador IA. Recibe la clave y un pedido con vehículo, kilometraje, tipo de servicio,
    servicio o síntoma e indicación del jefe de taller (si existe). Elige los conceptos del catálogo y
    devuelve la cotización calculada por el tarifario (items, total, repuestos bajo pedido y texto_cliente)."""
    ctx = runtime.context
    ctx.paso("orquestador", "agente_cotizador", "Delegando en el Agente Cotizador")
    r = await agente_cotizador_grafo().ainvoke(
        {"messages": [HumanMessage(f"Clave de la solicitud: {clave}\nPedido: {pedido}")]}, context=ctx)
    cotizaciones = _resultados(r["messages"], "cotizar")
    return json.dumps({"resultado": cotizaciones[-1] if cotizaciones else
                       {"ok": False, "error": "sin_cotizacion", "mensaje": "El cotizador no generó una cotización."},
                       "nota_cotizador": _nota(r["messages"])}, ensure_ascii=False)


@tool
async def agente_agenda(tarea: Literal["PROPONER", "RESERVAR"], clave: str, instruccion: str,
                        runtime: ToolRuntime[Contexto]) -> str:
    """Agente de Agenda IA. PROPONER: 3 turnos según la fecha deseada y la preferencia del cliente
    (p. ej. "el sábado en la tarde"). RESERVAR: reserva la opción que eligió el cliente (número 1, 2 o 3,
    o su descripción). Devuelve el resultado de la agenda con texto_cliente."""
    ctx = runtime.context
    ctx.paso("orquestador", "agente_agenda", f"Delegando en el Agente de Agenda ({tarea.lower()})")
    extra = ""
    sol = solicitudes.consultar(clave, ctx.session_id)
    if sol.get("misma_sesion"):
        s = sol["solicitud"]
        extra = f"\nFecha deseada registrada: {s['fecha_deseada']}."
        if tarea == "RESERVAR" and s.get("turnos_propuestos"):
            extra += "\nTurnos propuestos: " + json.dumps(s["turnos_propuestos"], ensure_ascii=False)
    r = await agente_agenda_grafo().ainvoke(
        {"messages": [HumanMessage(f"Tarea: {tarea}\nClave: {clave}\nInstrucción: {instruccion}{extra}")]},
        context=ctx)
    reservas = _resultados(r["messages"], "reservar_turno")
    propuestas = _resultados(r["messages"], "proponer_turnos")
    salida: dict[str, Any] = {"nota_agenda": _nota(r["messages"])}
    if tarea == "RESERVAR":
        res = reservas[-1] if reservas else {"ok": False, "error": "sin_reserva",
                                              "mensaje": "No se pudo identificar el turno elegido."}
        salida.update(reservado=bool(res.get("ok")), reserva=res)
        if propuestas:
            salida["alternativas"] = propuestas[-1]
        elif res.get("alternativas"):
            salida["alternativas"] = res["alternativas"]
    else:
        salida["propuesta"] = propuestas[-1] if propuestas else {"ok": False, "error": "sin_propuesta"}
    return json.dumps(salida, ensure_ascii=False)


HERRAMIENTAS_ORQUESTADOR = [h.validar_solicitud, h.mis_solicitudes, h.registrar_solicitud,
                            h.rechazar_solicitud, agente_cotizador, agente_agenda]


def crear_orquestador(checkpointer):
    s = settings()
    return create_agent(
        modelo(s.modelo_orquestador), HERRAMIENTAS_ORQUESTADOR,
        middleware=_middleware_comun("orquestador", s.modelo_orquestador, leer_prompt("orquestador"), s.ventana_memoria,
                                     s.max_llamadas_modelo),
        context_schema=Contexto, checkpointer=checkpointer, name="orquestador",
    )
