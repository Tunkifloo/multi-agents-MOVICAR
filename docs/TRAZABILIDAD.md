# Trazabilidad BPMN TO-BE → componentes de la v3 (LangChain)

Regla del Lab 02: **todo componente corresponde a un elemento del modelo; si no, sobra.** Fuente: `docs/MOVICAR_TO-BE.bpmn`.

## Canal y agentes

| Elemento del BPMN TO-BE | Componente v3 | Archivo |
|---|---|---|
| Mensaje de WhatsApp recibido (webhook) | Interfaz web + `POST /api/chat/{sid}/stream` | `frontend/src/vistas/Chat.tsx`, `backend/app/main.py` |
| Normalizar el mensaje / Extraer datos del vehículo y de la falla (LLM) | Agente Orquestador (`create_agent`) | `backend/app/agentes/grafo.py` · `prompts/orquestador.md` |
| Clasificar el servicio y estimar la confianza (LLM) | Agente Orquestador → argumentos de `registrar_solicitud` | ídem |
| (soporte: datos en varios mensajes) | Checkpointer de LangGraph + `PromptYVentana` (ventana de 20) | `backend/app/asistente.py`, `agentes/base.py` |
| (soporte de los agentes) | `ChatGoogleGenerativeAI` + `LimitadorRPM` + respaldo + reintentos | `backend/app/agentes/base.py` |
| Validar contra el contrato de entrada / ¿Cumple el contrato? | `validar_solicitud` → `contrato.validar_contrato` | `agentes/herramientas.py`, `app/contrato.py` |
| Calcular la clave de idempotencia | `contrato.calcular_clave` | `app/contrato.py` |
| ¿Clave ya registrada? / Reenviar la cita existente | `validar_solicitud` (campo `consulta`) y `mis_solicitudes` → `solicitudes.consultar` | `servicios/solicitudes.py` |
| ¿Preventivo y confianza ≥ 0,90? | `registrar_solicitud` → compuerta en `solicitudes.registrar` | `servicios/solicitudes.py` |
| Consultar stock y precios de repuestos | `agente_cotizador` · `consultar_catalogo` | `agentes/grafo.py`, `servicios/cotizacion.py` |
| Calcular la mano de obra según tarifario / Generar la cotización detallada / ¿Repuestos en stock? | `cotizar` → `cotizacion.cotizar` | `servicios/cotizacion.py` |
| Consultar la disponibilidad de mecánicos / Proponer tres turnos / Proponer nuevos turnos | `agente_agenda` · `proponer_turnos` → `agenda.proponer` | `servicios/agenda.py` |
| Crear el evento en la agenda y registrar la clave | `reservar_turno` → `agenda.reservar` (atómico) | `servicios/agenda.py` |
| ¿Qué responde el cliente? → no desea continuar | `rechazar_solicitud` → `solicitudes.rechazar` | `servicios/solicitudes.py` |

## Capa determinista (`backend/app/servicios`)

| Función | Regla que implementa |
|---|---|
| `estados.cambiar_estado` | Transiciones de `config/reglas.json` + traza en `historial_estados` |
| `solicitudes.detectar_sintomas` | Red de seguridad de la compuerta (E10: «es solo mantenimiento» con síntoma) |
| `cotizacion.catalogo_para_agente` | El agente ve el catálogo sin precios ni stock |
| `cotizacion.texto_cotizacion` / `agenda.texto_turnos` | El texto con montos y turnos lo genera el código |
| `agenda._reservar` | Reserva atómica, idempotente y solo sobre turnos propuestos |

## Flujos de soporte

| Elemento del BPMN TO-BE | Componente v3 |
|---|---|
| Validar diagnóstico y prioridad (Jefe de taller) | Panel del jefe (`frontend/src/vistas/Jefe.tsx`) → `POST /api/jefe/decision` → `jefe.decidir` |
| (no está en el BPMN; propuesto: SLA del jefe) | Worker · `programados.vencer_sla_revision` (cada 15 min) |
| Vencen 48 h sin respuesta / Enviar recordatorio y registrar seguimiento | Worker · `programados.seguimiento_48h` (cada hora) *(solo registra el seguimiento)* |
| Fallo de API tras 3 reintentos / Registrar en la cola de fallidos | `ModelRetryMiddleware` + `ModelFallbackMiddleware` → `asistente.responder` → `fallos.registrar` |
| (propuesto, Arquitectura-futuro: bucle de calibración) | `jefe.metricas_acuerdo` (panel del jefe y `scripts/metricas_acuerdo.py`) |
| (solo pruebas, se desactiva en la demostración) | `POST /api/pruebas` (`MODO_PRUEBAS=true`) |

## Elementos del BPMN no implementados (declarados)

| Elemento | Motivo |
|---|---|
| Vencen 24 h sin respuesta → Solicitud cerrada por datos incompletos | Sin fila registrada no hay qué cerrar; propuesto para v4 |
| Confirmar precio y plazo con el proveedor (Recepción) | Fuera del flujo: se marca `requiere_proveedor` y Recepción lo gestiona |
| Carril «Orquestador n8n (flujo determinista)» | La orquestación la hace un agente; lo determinista está en `app/servicios`. **Actualizar el BPMN TO-BE.** |
| Canal WhatsApp Business | Simulado por la interfaz web (decisión del curso: sin API de WhatsApp) |
