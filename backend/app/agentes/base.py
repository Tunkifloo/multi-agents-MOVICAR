"""Piezas comunes de los agentes: contexto de ejecución, modelo Gemini y middleware."""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Callable

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.rate_limiters import BaseRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI

from ..config import RAIZ, TZ, fecha_larga, settings

warnings.filterwarnings("ignore", message=".*fixed sampling defaults.*")


@dataclass
class Contexto:
    """Contexto de ejecución (runtime context de LangGraph).

    session_id viene del canal (la conversación), NUNCA del modelo: es el equivalente a inyectar
    `sessionId` desde el Chat Trigger en n8n. Las herramientas lo leen de aquí.
    """
    session_id: str
    emitir: Callable[[dict], None] | None = field(default=None, repr=False)

    def paso(self, agente: str, accion: str, detalle: str = "") -> None:
        if self.emitir:
            try:
                self.emitir({"tipo": "paso", "agente": agente, "accion": accion, "detalle": detalle})
            except Exception:  # pragma: no cover - el streaming nunca debe romper la herramienta
                pass


class CuotaLocalAgotada(RuntimeError):
    """La ventana de RPM del modelo está llena: ModelFallbackMiddleware pasa al modelo de respaldo."""


class LimitadorRPM(BaseRateLimiter):
    """Ventana deslizante de 60 s: como mucho `rpm` llamadas por minuto a un modelo.

    Si para llamar habría que esperar más de `espera_max` segundos, lanza CuotaLocalAgotada en lugar
    de bloquear, para que el middleware de respaldo pruebe con otro modelo (otra cuota).
    """

    def __init__(self, modelo: str, rpm: int, espera_max: float):
        self.modelo, self.rpm, self.espera_max = modelo, max(1, rpm), espera_max
        self._marcas: deque[float] = deque()
        self._lock = threading.Lock()

    def _espera(self) -> float:
        with self._lock:
            ahora = time.monotonic()
            while self._marcas and ahora - self._marcas[0] >= 60:
                self._marcas.popleft()
            if len(self._marcas) < self.rpm:
                self._marcas.append(ahora)
                return 0.0
            return 60 - (ahora - self._marcas[0]) + 0.05

    def acquire(self, *, blocking: bool = True) -> bool:
        while (w := self._espera()) > 0:
            if not blocking:
                return False
            if w > self.espera_max:
                raise CuotaLocalAgotada(f"{self.modelo}: cuota de {self.rpm} RPM llena (faltan {w:.0f} s)")
            time.sleep(w)
        return True

    async def aacquire(self, *, blocking: bool = True) -> bool:
        while (w := self._espera()) > 0:
            if not blocking:
                return False
            if w > self.espera_max:
                raise CuotaLocalAgotada(f"{self.modelo}: cuota de {self.rpm} RPM llena (faltan {w:.0f} s)")
            await asyncio.sleep(w)
        return True


@lru_cache
def limitador(nombre: str) -> LimitadorRPM:
    """Un limitador por modelo, compartido por todos los agentes que usan ese modelo."""
    s = settings()
    return LimitadorRPM(nombre, s.rpm(nombre), s.espera_max_cuota_seg)


@lru_cache
def modelo(nombre: str) -> ChatGoogleGenerativeAI:
    s = settings()
    return ChatGoogleGenerativeAI(
        model=nombre, google_api_key=s.google_api_key or None, temperature=s.temperatura,
        max_retries=0,  # reintentos (ModelRetryMiddleware) y respaldo (ModelFallbackMiddleware) en el agente
        timeout=30, rate_limiter=limitador(nombre),
    )


def leer_prompt(nombre: str) -> str:
    return (RAIZ / "prompts" / f"{nombre}.md").read_text(encoding="utf-8")


def calendario(dias: int = 14) -> str:
    hoy = datetime.now(TZ).date()
    partes = []
    for i in range(dias):
        d = hoy + timedelta(days=i)
        etiqueta = " (hoy)" if i == 0 else " (mañana)" if i == 1 else ""
        partes.append(f"{fecha_larga(d)} = {d.isoformat()}{etiqueta}")
    return "; ".join(partes)


def renderizar(plantilla: str) -> str:
    ahora = datetime.now(TZ)
    return (plantilla.replace("{{AHORA}}", f"{fecha_larga(ahora.date())} {ahora:%Y-%m-%d %H:%M}")
            .replace("{{CALENDARIO}}", calendario()))


log = logging.getLogger("movicar.llm")


class RegistroLLM(AgentMiddleware):
    """Registra cada intento de llamada al modelo (modelo real usado, latencia y error).

    Va DENTRO del middleware de respaldo, así que ve el modelo efectivo de cada intento.
    """

    def __init__(self, agente: str):
        super().__init__()
        self.agente = agente

    def _nombre(self, request: ModelRequest) -> str:
        return getattr(request.model, "model", "?").replace("models/", "")

    def wrap_model_call(self, request: ModelRequest, handler: Callable) -> Any:
        t0 = time.monotonic()
        try:
            r = handler(request)
            log.info("%s · %s · %.1f s", self.agente, self._nombre(request), time.monotonic() - t0)
            return r
        except Exception as e:
            log.warning("%s · %s · %.1f s · %s: %s", self.agente, self._nombre(request), time.monotonic() - t0,
                        type(e).__name__, str(e)[:160])
            raise

    async def awrap_model_call(self, request: ModelRequest, handler: Callable) -> Any:
        t0 = time.monotonic()
        try:
            r = await handler(request)
            log.info("%s · %s · %.1f s", self.agente, self._nombre(request), time.monotonic() - t0)
            return r
        except Exception as e:
            log.warning("%s · %s · %.1f s · %s: %s", self.agente, self._nombre(request), time.monotonic() - t0,
                        type(e).__name__, str(e)[:160])
            raise


class PromptYVentana(AgentMiddleware):
    """Prompt de sistema dinámico (fecha de Lima en cada llamada) + memoria de ventana.

    La ventana recorta lo que VE el modelo (no el estado guardado) y siempre empieza en un mensaje
    del cliente, para no partir pares llamada/resultado de herramienta.
    """

    def __init__(self, plantilla: str, ventana: int | None = None):
        super().__init__()
        self.plantilla = plantilla
        self.ventana = ventana

    def _preparar(self, request: ModelRequest) -> ModelRequest:
        msgs = list(request.messages)
        if self.ventana and len(msgs) > self.ventana:
            corte = len(msgs) - self.ventana
            while corte < len(msgs) and not isinstance(msgs[corte], HumanMessage):
                corte += 1
            if corte < len(msgs):
                msgs = msgs[corte:]
        return request.override(system_message=SystemMessage(renderizar(self.plantilla)), messages=msgs)

    def wrap_model_call(self, request: ModelRequest, handler: Callable) -> Any:
        return handler(self._preparar(request))

    async def awrap_model_call(self, request: ModelRequest, handler: Callable) -> Any:
        return await handler(self._preparar(request))
