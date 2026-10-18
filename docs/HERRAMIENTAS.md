# Contratos de las herramientas (LangChain)

Cada herramienta (`backend/app/agentes/herramientas.py`) es una envoltura delgada sobre la capa determinista (`backend/app/servicios/`). Todas devuelven JSON con la forma `{ ok: boolean, ... }`. Cuando `ok:false`, incluyen `error` (código corto) y `mensaje` (texto que el agente puede explicar al cliente). **Un error de negocio nunca es una excepción**; las excepciones se reservan para fallos técnicos, que terminan en `cola_fallidos`.

- `session_id` llega por `ToolRuntime[Contexto]` (runtime context), **nunca** como argumento del modelo.
- Las constantes (umbral, días máximos, plazos, transiciones) se leen de `config/reglas.json`.
- La validación y el hash viven en `backend/app/contrato.py`, port 1:1 de `scripts/lib/contrato.js` (paridad verificada con Node).

---

## validar_solicitud (orquestador)

**Entrada (IA):** `telefono`, `placa`, `vehiculo`, `kilometraje` (0 si no lo sabe), `fecha_deseada` (AAAA-MM-DD), `descripcion_falla`.

| Campo | Regla | Normalización |
|---|---|---|
| telefono | Celular peruano de 9 dígitos que empieza en 9, o E.164 de 10 a 15 dígitos | `987 654 321` → `+51987654321` |
| placa | 6 alfanuméricos | `bxr742` → `BXR-742` |
| vehiculo | De 3 a 80 caracteres | Recortado |
| fecha_deseada | Entre hoy y hoy + 60 días (Lima), **no domingo** | ISO |
| descripcion_falla | De 1 a 500 caracteres | Recortada |
| kilometraje | Entero ≥ 0 | 0 por defecto |

**Salida:** `{ valido, errores[], clave, datos{...}, consulta }`. Con `valido:false`, `clave` es `""` y `errores` lista **todos** los problemas. Con `valido:true`, `consulta` trae el resultado de *¿Clave ya registrada?* (ver `consultar`), para ahorrar una llamada al modelo.

## mis_solicitudes (orquestador)

Sin argumentos. Devuelve las hasta 3 solicitudes más recientes **de esta conversación** con su estado, cotización y turnos. Se usa cuando el cliente escribe «estado».

## consultar (interno, dentro de validar_solicitud)

- No existe: `{ ok:true, existe:false }`
- Otra sesión: `{ ok:true, existe:true, misma_sesion:false }`, sin ningún otro campo.
- Misma sesión: `{ ok:true, existe:true, misma_sesion:true, solicitud:{ clave, estado, vehiculo, placa, fecha_deseada, tipo_servicio, prioridad, especialidad, observacion_jefe, total_cotizacion, cotizacion_detalle, requiere_proveedor, turnos_propuestos, turno_confirmado } }`

## registrar_solicitud (orquestador)

**Entrada (IA):** los 6 campos crudos + `tipo_servicio_agente` (`preventivo`/`correctivo`), `confianza_agente` (0–1), `prioridad_sugerida` (`normal`/`alta`), `especialidad_sugerida` (`general`/`motor_electrico`/`frenos_suspension`). Los enumerados son `Literal` en el esquema.

1. Revalida el contrato. Si no es válido → `{ok:false, error:"contrato", errores}`.
2. Si la clave ya existe → `{ok:true, ya_existia:true, clave, estado}` sin modificarla; con otro `session_id` → `{ok:true, ya_existia:true, misma_sesion:false}`.
3. Compuerta: `correctivo`, `confianza_agente < UMBRAL` o síntoma detectado en la descripción → `revision_jefe`; si no → `lista_para_cotizar`. Confianza ausente o fuera de 0–1 se trata como 0.
4. Inserta con `creado_en = ts_estado = ahora` y `especialidad = general` si es preventivo; traza en `historial_estados`.
5. Responde `{ok:true, ya_existia:false, clave, estado, motivo_revision}`.

## rechazar_solicitud (orquestador)

**Entrada (IA):** `clave`. Solo pasa a `rechazada` si la solicitud es de esta sesión y la transición lo permite. `{ok:true, estado:"rechazada"}` o `{ok:false, error:"transicion_invalida", estado_actual}`.

## agente_cotizador (orquestador → subagente)

**Entrada (IA):** `clave`, `pedido` (vehículo, km, tipo, síntoma o servicio, indicación del jefe). **Salida:** `{ resultado: <salida de cotizar>, nota_cotizador }`.

## agente_agenda (orquestador → subagente)

**Entrada (IA):** `tarea` (`PROPONER`/`RESERVAR`), `clave`, `instruccion` (preferencia del cliente u opción elegida). La herramienta agrega a la instrucción la fecha deseada y, para RESERVAR, los turnos propuestos.
**Salida:** PROPONER → `{ propuesta: <salida de proponer_turnos> }`; RESERVAR → `{ reservado, reserva: <salida de reservar_turno>, alternativas? }`.

---

## consultar_catalogo (cotizador)

Devuelve `codigo, concepto, tipo, categoria, especialidad, aplica_a`. **Sin `precio_unitario` ni `stock`**: el agente no los necesita y así no puede transcribirlos.

## cotizar (cotizador · `return_direct`)

**Entrada (IA):** `clave`, `items: [{ codigo, cantidad (1–10) }]`.

1. La solicitud debe ser de esta sesión y estar en `lista_para_cotizar`, `validada_jefe` o `cotizada` → si no, `estado_no_cotizable`.
2. Cada código debe existir en el catálogo; códigos repetidos se suman; cantidad entera de 1 a 10.
3. Códigos inexistentes o lista vacía → `{ok:false, error:"items_invalidos", detalle}`. **Nada se descarta en silencio y nada se guarda.**
4. `subtotal = cantidad × precio_unitario` (2 decimales), `bajo_pedido = repuesto && stock < cantidad`, `total`, `requiere_proveedor`.
5. Guarda y pasa a `cotizada`.
6. `{ok:true, items[], total, repuestos_bajo_pedido[], requiere_proveedor, texto_cliente}`; `texto_cliente` es el Markdown generado por código que el orquestador pega tal cual.

## proponer_turnos (agenda · `return_direct`)

**Entrada (IA):** `clave`, `fecha_desde` (AAAA-MM-DD), `franja` (`manana` | `tarde` | `cualquiera`).

1. Estado `cotizada` o `sin_confirmar_seguimiento`. La **especialidad se toma de la fila**.
2. `fecha_desde` anterior a hoy → hoy; domingo → lunes. Se descartan los turnos de hoy que ya pasaron.
3. Turnos `libre` de esa especialidad desde `fecha_desde`, en la franja pedida, en orden cronológico: los 3 primeros.
4. Si hay menos de 3, se completa con otras franjas y `franja_relajada:true`.
5. Guarda las 3 opciones numeradas en `turnos_propuestos` (la reserva solo se permite sobre ellas).
6. `{ok:true, especialidad, desde, franja, franja_relajada, opciones:[{opcion, turno_id, fecha, dia_semana, hora, mecanico}], texto_cliente}`.

## reservar_turno (agenda · `return_direct`)

**Entrada (IA):** `clave` y `opcion` (1–3) o `turno_id`.

1. Si ya está `agendada` con ese turno → `{ok:true, ya_reservado:true, turno}` (idempotente); con otro turno → `ya_agendada`.
2. Estado `cotizada` o `sin_confirmar_seguimiento`, y el turno debe estar entre los propuestos → si no, `turno_no_propuesto`.
3. `UPDATE agenda SET estado='reservado', clave_solicitud=:clave WHERE turno_id=:id AND estado='libre'` (atómico).
4. Si no afectó filas y el turno no es de esta clave → `{ok:false, error:"turno_ocupado", alternativas:<proponer_turnos desde la misma fecha>}`.
5. Pasa a `agendada` con `turno_confirmado`. `{ok:true, turno, texto_cliente}`.

---

## API del personal (Basic Auth: `JEFE_USUARIO` / `JEFE_CLAVE`)

| Ruta | Efecto |
|---|---|
| `GET /api/jefe/pendientes` | Casos en `revision_jefe` o `escalada_recepcion` con antigüedad y `sla_vencido` |
| `POST /api/jefe/decision` | `{clave, decision: aprobar\|rechazar, tipo_servicio, prioridad, especialidad, observacion}`. Aprobar exige observación → `validada_jefe`; rechazar → `rechazada` |
| `GET /api/jefe/metricas` | Acuerdo agente-jefe y si se cumple la puerta (≥ 30 casos y ≥ 90 %) |
| `GET /api/solicitudes[/{clave}]` | Listado y detalle con `historial` |
| `GET /api/agenda`, `/api/catalogo`, `/api/fallos`, `/api/resumen` | Vistas de back-office |
| `POST /api/programados/ejecutar` | Ejecuta ahora el SLA de 2 h, el seguimiento de 48 h y la extensión de la agenda |

## Utilidad de pruebas (`POST /api/pruebas`, cabecera `X-Test-Token`, solo con `MODO_PRUEBAS=true`)

| `accion` | Parámetros | Efecto |
|---|---|---|
| `get_solicitud` | `session_id` | Fila completa más reciente de esa sesión |
| `aprobar_jefe` | `clave`, `tipo_servicio`, `prioridad`, `especialidad`, `observacion` | Igual que el panel |
| `ocupar_turno` | `turno_id` | Lo marca `reservado` con la clave `TEST-OCUPADO` |
| `envejecer` | `clave`, `horas` | Resta horas a `ts_estado` |
| `contar` | `session_id` | `{n}` filas de esa sesión |
| `listar` | — | Todas las filas (para `metricas_acuerdo.py`) |
| `correr_programados` | — | Misma lógica que el worker |
| `reset` | — | Borra las solicitudes con teléfono `+5190000…` y libera sus turnos |
