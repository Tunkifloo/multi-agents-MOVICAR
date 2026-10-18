"""Configuración: variables de entorno (.env) + reglas de negocio protegidas (config/reglas.json).

Las reglas (umbral 0,90, plazos, transiciones) NO se escriben en el código ni en los prompts:
se leen siempre de config/reglas.json, que es un elemento protegido del proyecto.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del proyecto (contiene config/, datos/, prompts/). En Docker es /app.
RAIZ = Path(os.environ.get("MOVICAR_RAIZ") or Path(__file__).resolve().parents[2])
TZ = ZoneInfo("America/Lima")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(RAIZ / ".env"), env_file_encoding="utf-8", extra="ignore")

    google_api_key: str = ""
    # Modelos (Gemini 2.5 Flash ya no está disponible para cuentas nuevas de AI Studio).
    # Cada modelo tiene su propia cuota por minuto en el plan gratuito: se reparten los agentes.
    modelo_orquestador: str = "gemini-3.5-flash-lite"
    modelo_subagentes: str = "gemini-3.1-flash-lite"
    modelos_respaldo: str = "gemini-3.1-flash-lite,gemini-3.5-flash-lite,gemini-3.5-flash"
    limites_rpm: str = "gemini-3.5-flash=5,gemini-3.5-flash-lite=14,gemini-3.1-flash-lite=14"
    rpm_por_defecto: int = 10
    espera_max_cuota_seg: float = 4.0        # más espera que esto → se pasa al modelo de respaldo
    temperatura: float = 0.2
    llm_reintentos: int = 3                  # BPMN: «Fallo de API tras 3 reintentos»
    max_llamadas_modelo: int = 15            # equivalente a maxIterations del agente de n8n
    ventana_memoria: int = 20                # mensajes que ve el modelo (memoria de ventana)

    database_url: str = ""                   # vacío → SQLite local en backend/data/
    catalogo_csv: str = "datos/catalogo_servicios_real_v2.csv"
    dias_agenda: int = 21

    jefe_usuario: str = "jefe"
    jefe_clave: str = ""                     # obligatoria en .env: sin clave, el panel del personal queda cerrado
    modo_pruebas: bool = False
    test_token: str = ""

    cors_origenes: str = "http://localhost:5173,http://localhost:8088"

    def rpm(self, modelo: str) -> int:
        tabla = dict(p.split("=") for p in self.limites_rpm.split(",") if "=" in p)
        return int(tabla.get(modelo, self.rpm_por_defecto))

    @property
    def respaldos(self) -> list[str]:
        return [m.strip() for m in self.modelos_respaldo.split(",") if m.strip()]

    @property
    def url_bd(self) -> str:
        if self.database_url:
            return self.database_url
        carpeta = RAIZ / "backend" / "data"
        carpeta.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(carpeta / 'movicar.db').as_posix()}"


@lru_cache
def settings() -> Settings:
    return Settings()


@lru_cache
def reglas() -> dict:
    return json.loads((RAIZ / "config" / "reglas.json").read_text(encoding="utf-8"))


def ahora_utc() -> datetime:
    return datetime.now(timezone.utc)


def hoy_lima() -> date:
    return datetime.now(TZ).date()


def a_utc(dt: datetime | None) -> datetime | None:
    """SQLite devuelve datetimes sin zona: se asumen UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def fecha_larga(d: date) -> str:
    return f"{DIAS_SEMANA[d.weekday()]} {d.day} de {MESES[d.month - 1]}"
