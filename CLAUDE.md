# MOVICAR · Asistente multiagente de cotizaciones y citas (v3 · LangChain)

Proyecto del curso Automatización Inteligente de Procesos (UPAO). Se automatiza **«Cotizar repuestos y mano de obra y agendar la cita del vehículo»** de MOVICAR Taller Mecánico con **LangChain 1.x + LangGraph + Gemini + FastAPI + PostgreSQL + React**, levantado con **Docker Compose**. Es la réplica de la v2 multiagente de n8n (patrón supervisor). Ya no se usa n8n: ni su API ni su chat (`archivo_n8n/` es solo referencia).
Responde siempre en **español**.

## Lee esto antes de tocar nada
1. `README.md`: cómo se levanta y cómo se prueba.
2. `docs/ARQUITECTURA.md`: qué se construye y por qué (la sección 8 lista los defectos de la v2 que NO se deben repetir).
3. `docs/HERRAMIENTAS.md`: contratos exactos de cada herramienta.
4. `docs/DEFECTOS.md`: lo que ya falló y cómo se corrigió (cuotas de Gemini, timeouts).

## Principio de diseño (no negociable)
**La IA decide qué hacer y cuándo; el código garantiza cómo se hace.**
- `backend/app/agentes/` no importa la base de datos: las herramientas solo llaman a `backend/app/servicios/`.
- Ninguna herramienta recibe del modelo `estado`, `session_id`, precio, stock ni total. `session_id` llega por `ToolRuntime[Contexto]`.
- El estado solo cambia según `config/reglas.json → transiciones` (`servicios/estados.py`). La compuerta de riesgo vive en `servicios/solicitudes.py`, no en el prompt.
- Los servicios responden `{ok:false, error, mensaje}` ante errores de negocio; no lanzan excepciones por eso.
- Los montos y turnos que ve el cliente los redacta el código (`texto_cliente`); el orquestador los copia.

## Elementos protegidos (un hook bloquea su edición)
`config/reglas.json` · `datos/catalogo_servicios.csv` · `tests/escenarios.json` · `scripts/lib/contrato.js` · `scripts/proteger.py`
Si crees que hay que cambiar uno: **muestra el diff propuesto, explica el motivo y espera la aprobación del equipo.** Nunca debilites una prueba para que pase. `backend/app/contrato.py` debe seguir produciendo las mismas claves que `contrato.js` (lo verifica `test_contrato.py`).

## Controles automáticos
- **PreToolUse:** `scripts/proteger.py` bloquea la edición de los elementos protegidos.
- **PostToolUse:** `scripts/verificar_codigo.py` revisa el archivo editado (secretos, agentes con acceso a la BD, argumentos prohibidos en herramientas, umbral escrito a mano). Si falla, corrige antes de seguir.

## Comandos
```bash
docker compose up -d --build                       # http://localhost:8088
cd backend && .venv/Scripts/python -m pytest -q    # 47 pruebas sin LLM
node scripts/lib/contrato.test.js                  # 12 pruebas del contrato original
python scripts/probar_escenarios.py [E01 …]        # 14 conversaciones con Gemini real
python scripts/verificar_codigo.py                 # controles de arquitectura
docker compose logs -f api                         # agente · modelo · segundos por llamada
```

## Definición de «terminado»
1. `pytest` y `contrato.test.js` pasan; `verificar_codigo.py` sin errores.
2. Los escenarios afectados pasan con `probar_escenarios.py` (pega la tabla de `tests/resultados/*.md`).
3. `docs/TRAZABILIDAD.md` actualizado si se agrega un componente.
4. **No digas que algo funciona si no ejecutaste la prueba que lo demuestra.**

## Cuotas de Gemini
Plan gratuito: cuota por minuto **por modelo** (3.5-flash: 5; 3.5-flash-lite y 3.1-flash-lite: 15). No agregues llamadas al modelo por turno sin necesidad; el banco completo usa ~200 llamadas.

## Datos
Todos ficticios. Teléfonos de prueba `+5190000…`. Nunca escribas datos personales reales ni credenciales en el repositorio. `.env` está excluido de git y no se lee.
