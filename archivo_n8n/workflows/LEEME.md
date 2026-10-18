# workflows/ · fuente de los flujos de n8n

Un archivo JSON por flujo, en formato de exportación de n8n (`name`, `nodes`, `connections`, `settings`). Claude Code los crea aquí; `scripts/n8n_deploy.py` los publica.

## Archivos y nombres (exactos)

| Archivo | `name` del flujo |
|---|---|
| `01_registro_fallos.json` | MOVICAR · Registro de fallos |
| `10_sw_consultar_solicitud.json` | sw_consultar_solicitud |
| `11_sw_registrar_solicitud.json` | sw_registrar_solicitud |
| `12_sw_rechazar_solicitud.json` | sw_rechazar_solicitud |
| `13_sw_cotizar.json` | sw_cotizar |
| `14_sw_proponer_turnos.json` | sw_proponer_turnos |
| `15_sw_reservar_turno.json` | sw_reservar_turno |
| `20_asistente.json` | MOVICAR · Asistente |
| `30_pendientes_jefe.json` | MOVICAR · Pendientes del jefe |
| `31_bandeja_jefe.json` | MOVICAR · Bandeja del jefe |
| `40_sla_revision.json` | MOVICAR · SLA revisión 2 h |
| `41_seguimiento_48h.json` | MOVICAR · Seguimiento 48 h |
| `90_utilidad_pruebas.json` | MOVICAR · Utilidad de pruebas |

## Marcadores (nunca escribir el valor real a mano)

| Marcador | Se reemplaza por |
|---|---|
| `__PROMPT:orquestador__`, `__PROMPT:cotizador__`, `__PROMPT:agenda__` | Contenido de `prompts/*.md` |
| `__CONTRATO__` | `scripts/lib/contrato.js` (define `validarContrato` y `calcularClave`) |
| `__UMBRAL_CONFIANZA__`, `__SLA_REVISION_HORAS__`, `__SEGUIMIENTO_HORAS__`, `__DIAS_MAX_ANTICIPACION__` | `config/reglas.json` |
| `__TRANSICIONES__`, `__ESTADOS_COTIZABLES__`, `__ESTADOS_RESERVABLES__` | JSON de `config/reglas.json` (usar `JSON.parse('__TRANSICIONES__')`) |
| `__DT:movicar_solicitudes__` (y las otras tablas) | ID de la Data Table (`config/n8n_ids.json`) |
| `__WF:sw_cotizar__` (y los otros subflujos), `__WF:registro_fallos__` | ID del flujo, que completa el despliegue |

Ejemplo dentro de un nodo Code de `sw_registrar_solicitud`:
```js
__CONTRATO__
const UMBRAL = Number('__UMBRAL_CONFIANZA__');
const r = validarContrato($json);
if (!r.valido) return [{ json: { ok: false, error: 'contrato', errores: r.errores } }];
const conf = Number($json.confianza_agente);
const confianza = Number.isFinite(conf) && conf >= 0 && conf <= 1 ? conf : 0;
const estado = ($json.tipo_servicio_agente === 'correctivo' || confianza < UMBRAL) ? 'revision_jefe' : 'lista_para_cotizar';
```

## Notas de n8n verificadas en la v2 (`referencia/v2/`)
- Herramienta de Data Table de un agente: `n8n-nodes-base.dataTableTool` (aquí solo `operation: get`).
- Subagente: `@n8n/n8n-nodes-langchain.agentTool`. Herramienta de código: `@n8n/n8n-nodes-langchain.toolCode`.
- Los agentes Gemini vía n8n fallan con llamadas a herramientas en paralelo (defecto D1 de la v2): el prompt exige una herramienta por turno.
- `session_id` del chat: `{{ $('Mensaje del cliente recibido').item.json.sessionId }}`. **Verificar** que la expresión se resuelve dentro de las herramientas de los subagentes; si no, el orquestador debe pasarlo explícitamente y hay que documentarlo.
- Herramienta que llama a un subflujo: *Call n8n Workflow Tool* (`@n8n/n8n-nodes-langchain.toolWorkflow`); el subflujo empieza con *Execute Workflow Trigger* con entradas definidas. Confirmar el tipo y la versión exactos en la instancia antes de escribir el JSON.
