# Plan de construcción (v3 · LangChain) y estado

El plan original del paquete apuntaba a n8n (fases 0–7). Al migrar al ecosistema LangChain se conservan los mismos criterios de aceptación; cambia la plataforma. Cada fase se da por terminada solo cuando sus pruebas **se ejecutaron**.

| Fase | Contenido | Criterio | Estado (17/10/2026) |
|---|---|---|---|
| 0 | `.env` con la clave de Gemini; catálogo real exportado de la v2 (`datos/catalogo_servicios_real_v2.csv`) | Clave verificada contra la API | ✅ |
| 1 | Base del repositorio, controles (`proteger.py`, `verificar_codigo.py`) y contrato | `contrato.test.js` 12/12; hooks bloquean una violación de prueba | ✅ |
| 2 | Capa determinista (`app/servicios`) y utilidad de pruebas | Los 13 casos sin LLM (`backend/tests/test_servicios.py`, más casos extra) | ✅ 47/47 con contrato y API |
| 3 | Orquestador + subagentes (LangChain) y API | `probar_escenarios.py E01 E02 E03 E04` | ✅ |
| 4 | Humano en el bucle: panel del jefe, SLA 2 h, seguimiento 48 h | `E05 E12 E14` + aprobación desde el panel real | ✅ (aprobación hecha desde la interfaz) |
| 5 | Robustez | `E06 E07 E09 E10 E11 E13` + fallo del modelo → `cola_fallidos` | ✅ escenarios; fallo real de cuota (429) registrado como `transitorio` en la corrida inicial |
| 6 | Estabilidad | 14 escenarios con `--repeticiones 3` y evaluación de clasificación (40 mensajes) | ⏳ pendiente: consume ~600 llamadas al modelo; conviene correrlo con una clave de pago o repartido en días |
| 7 | Demostración | `MODO_PRUEBAS=false`, agenda desde el día de la demo, E01 y E05 en verde una hora antes | ⏳ antes de la exposición |
| Docker | `docker compose up -d --build` (db, api, worker, web) | 14/14 escenarios contra el stack dockerizado | ✅ |

## Pendientes recomendados
- Fase 6: `tests/clasificacion.csv` (20 preventivos, 15 correctivos, 5 ambiguos) y `scripts/evaluar_clasificacion.py`; criterio: 0 correctivos sin revisión.
- Actualizar la hoja «Idempotencia» del Lab 02 (la clave ya no lleva `tipo_servicio`) y el BPMN TO-BE (el carril del orquestador determinista ahora es un agente).
