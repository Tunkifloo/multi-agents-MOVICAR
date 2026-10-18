# MOVICAR · backend (API FastAPI + worker de tareas programadas). Contexto de build: raíz del proyecto.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    MOVICAR_RAIZ=/app TZ=America/Lima

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

# Reglas protegidas, catálogo y prompts: fuente única compartida con la documentación
COPY config/ config/
COPY datos/ datos/
COPY prompts/ prompts/
COPY backend/app/ backend/app/

RUN useradd --create-home --uid 1000 movicar && mkdir -p backend/data && chown -R movicar /app
USER movicar
WORKDIR /app/backend

EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/api/salud',timeout=4).status==200 else 1)"

# Un solo proceso: el limitador de cuota por modelo vive en memoria.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
