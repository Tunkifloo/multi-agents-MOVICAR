"""Worker de tareas programadas (equivale a los Schedule Trigger de n8n).

  cada 15 min → SLA de revisión del jefe (2 h)         → escalada_recepcion
  cada hora   → seguimiento de cotizaciones (48 h)     → sin_confirmar_seguimiento
  cada día    → asegurar la agenda de los próximos días (la agenda no caduca)

Uso:  python -m app.worker
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler

from . import db
from .config import TZ
from .servicios import fallos, programados

logging.basicConfig(level=logging.INFO, format="%(asctime)s worker %(levelname)s %(message)s")
log = logging.getLogger("movicar.worker")


def _tarea(nombre, fn):
    def envoltura():
        try:
            r = fn()
            log.info("%s → %s", nombre, r)
        except Exception as e:  # el fallo de un flujo programado también va a la cola de fallidos
            log.exception("%s falló", nombre)
            fallos.registrar(f"MOVICAR · {nombre}", "worker", e, {}, intentos=1)
    return envoltura


def main() -> None:
    db.inicializar()
    s = BlockingScheduler(timezone=TZ)
    s.add_job(_tarea("SLA revisión 2 h", programados.vencer_sla_revision), "interval", minutes=15, next_run_time=None)
    s.add_job(_tarea("Seguimiento 48 h", programados.seguimiento_48h), "interval", hours=1)
    s.add_job(_tarea("Agenda", db.asegurar_agenda), "cron", hour=0, minute=5)
    _tarea("arranque", programados.correr_todos)()
    log.info("Worker iniciado (zona America/Lima)")
    s.start()


if __name__ == "__main__":
    main()
