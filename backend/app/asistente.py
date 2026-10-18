"""Servicio de conversación: ejecuta el orquestador por sesión y emite eventos para la interfaz.

- Memoria por sesión: checkpointer de LangGraph (PostgreSQL en Docker, SQLite en local).
- Eventos: «paso» (qué agente/herramienta trabaja), «respuesta», «error».
- Fallos técnicos (tras los reintentos del middleware) → cola_fallidos + respuesta amable al cliente.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import AsyncExitStack
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage
from sqlalchemy import asc, desc, insert, select, update

from .agentes.base import Contexto
from .agentes.grafo import crear_orquestador
from .config import RAIZ, ahora_utc, settings
from .db import conversaciones, engine, fila_a_dict, mensajes
from .servicios import fallos

MENSAJE_FALLO = ("Disculpa, tuvimos un problema técnico al procesar tu mensaje. Ya quedó registrado y el "
                 "equipo de MOVICAR lo revisará. Por favor, inténtalo de nuevo en unos minutos.")


class Asistente:
    def __init__(self) -> None:
        self._pila = AsyncExitStack()
        self.checkpointer = None
        self.agente = None

    async def iniciar(self) -> None:
        url = settings().url_bd
        if url.startswith("postgresql"):
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            conninfo = url.replace("postgresql+psycopg://", "postgresql://")
            self.checkpointer = await self._pila.enter_async_context(AsyncPostgresSaver.from_conn_string(conninfo))
            await self.checkpointer.setup()
        else:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            ruta = (RAIZ / "backend" / "data" / "checkpoints.db") if "memory" not in url else ":memory:"
            self.checkpointer = await self._pila.enter_async_context(AsyncSqliteSaver.from_conn_string(str(ruta)))
        self.agente = crear_orquestador(self.checkpointer)

    async def cerrar(self) -> None:
        await self._pila.aclose()

    # ------------------------------------------------------------------ conversaciones ----
    @staticmethod
    def nueva_conversacion(titulo: str = "Nueva conversación") -> dict:
        sid = "web-" + uuid.uuid4().hex[:16]
        ahora = ahora_utc()
        with engine().begin() as c:
            c.execute(insert(conversaciones).values(session_id=sid, titulo=titulo, creado_en=ahora, actualizado_en=ahora))
        return {"session_id": sid, "titulo": titulo, "creado_en": ahora.isoformat()}

    @staticmethod
    def _asegurar_conversacion(sid: str, primer_mensaje: str) -> None:
        ahora = ahora_utc()
        titulo = (primer_mensaje.strip().splitlines() or ["Conversación"])[0][:60]
        with engine().begin() as c:
            fila = c.execute(select(conversaciones).where(conversaciones.c.session_id == sid)).first()
            if not fila:
                c.execute(insert(conversaciones).values(session_id=sid, titulo=titulo, creado_en=ahora, actualizado_en=ahora))
            else:
                valores = {"actualizado_en": ahora}
                if fila.titulo == "Nueva conversación":
                    valores["titulo"] = titulo
                c.execute(update(conversaciones).where(conversaciones.c.session_id == sid).values(**valores))

    @staticmethod
    def _guardar_mensaje(sid: str, rol: str, contenido: str, pasos: list | None = None, seg: float | None = None) -> None:
        with engine().begin() as c:
            c.execute(insert(mensajes).values(session_id=sid, rol=rol, contenido=contenido,
                                              pasos=json.dumps(pasos, ensure_ascii=False) if pasos else None,
                                              segundos=seg, creado_en=ahora_utc()))

    @staticmethod
    def listar_conversaciones(limite: int = 50) -> list[dict]:
        with engine().connect() as c:
            return [fila_a_dict(r) for r in c.execute(select(conversaciones)
                                                      .order_by(desc(conversaciones.c.actualizado_en)).limit(limite))]

    @staticmethod
    def mensajes_de(sid: str) -> list[dict]:
        with engine().connect() as c:
            filas = c.execute(select(mensajes).where(mensajes.c.session_id == sid).order_by(asc(mensajes.c.id))).all()
        out = []
        for r in filas:
            d = fila_a_dict(r)
            d["pasos"] = json.loads(d["pasos"]) if d.get("pasos") else []
            out.append(d)
        return out

    # ------------------------------------------------------------------ ejecución ---------
    async def responder(self, sid: str, texto: str) -> AsyncIterator[dict[str, Any]]:
        """Ejecuta un turno del orquestador y va emitiendo eventos."""
        texto = (texto or "").strip()[:2000]
        self._asegurar_conversacion(sid, texto)
        self._guardar_mensaje(sid, "cliente", texto)
        cola: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        ctx = Contexto(session_id=sid, emitir=lambda ev: loop.call_soon_threadsafe(cola.put_nowait, ev))
        pasos: list[dict] = []
        t0 = time.time()
        tarea = asyncio.create_task(self.agente.ainvoke(
            {"messages": [HumanMessage(texto)]},
            config={"configurable": {"thread_id": sid}, "run_name": "movicar_turno",
                    "metadata": {"session_id": sid}, "tags": ["movicar"]},
            context=ctx))
        yield {"tipo": "paso", "agente": "orquestador", "accion": "pensando", "detalle": "Analizando tu mensaje"}
        while not tarea.done() or not cola.empty():
            try:
                ev = await asyncio.wait_for(cola.get(), timeout=0.25)
                pasos.append(ev)
                yield ev
            except asyncio.TimeoutError:
                continue
        seg = round(time.time() - t0, 1)
        try:
            resultado = tarea.result()
            final = resultado["messages"][-1]
            respuesta = (final.text or "").strip() if final.type == "ai" else ""
            if not respuesta:
                raise RuntimeError("El orquestador terminó sin una respuesta de texto (límite de llamadas alcanzado)")
            self._guardar_mensaje(sid, "asistente", respuesta, pasos, seg)
            yield {"tipo": "respuesta", "contenido": respuesta, "segundos": seg, "pasos": pasos}
        except Exception as e:  # fallo técnico: después de los reintentos del middleware
            fila = fallos.registrar("MOVICAR · Asistente (orquestador)", f"{sid}:{int(t0)}", e,
                                    {"session_id": sid, "mensaje": texto[:500], "pasos": [p.get("accion") for p in pasos]},
                                    intentos=settings().llm_reintentos + 1)
            self._guardar_mensaje(sid, "error", MENSAJE_FALLO, pasos, seg)
            yield {"tipo": "error", "contenido": MENSAJE_FALLO, "clase_error": fila["clase_error"], "segundos": seg}

    async def responder_completo(self, sid: str, texto: str) -> dict[str, Any]:
        ultimo: dict[str, Any] = {}
        pasos = []
        async for ev in self.responder(sid, texto):
            if ev["tipo"] == "paso":
                pasos.append(ev)
            else:
                ultimo = ev
        return {"respuesta": ultimo.get("contenido", ""), "tipo": ultimo.get("tipo"), "segundos": ultimo.get("segundos"),
                "pasos": pasos}


asistente = Asistente()
