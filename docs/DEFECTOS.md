# Defectos encontrados durante la construcción (v3 · LangChain)

Formato de la tabla D1–D5 del informe v2: id, evidencia, causa, corrección y re-prueba.

| Id | Evidencia | Causa | Corrección | Re-prueba |
|---|---|---|---|---|
| L1 | `gemini-2.5-flash` → 404 «no longer available to new users» | Google retiró Gemini 2.5 Flash para cuentas nuevas de AI Studio | Modelos configurables por `.env`; por defecto `gemini-3.5-flash-lite` (orquestador) y `gemini-3.1-flash-lite` (subagentes), elegidos por latencia medida (1–2 s por llamada) | Humo E01 OK |
| L2 | Segundo turno de E01 → `429 RESOURCE_EXHAUSTED … limit: 5` y respuesta de fallo (la reserva sí se hizo) | Plan gratuito: `gemini-3.5-flash` permite 5 solicitudes por minuto por modelo; un turno completo usa 5–8 | Cuotas medidas por modelo; `LimitadorRPM` (ventana de 60 s); `ModelFallbackMiddleware` cambia de modelo ante 429 o cuota llena; menos llamadas por turno (`validar_solicitud` incluye la consulta; herramientas finales `return_direct`; alternativas deterministas ante turno ocupado) | 14/14 escenarios; 0 filas en `cola_fallidos` aunque el log registra decenas de cambios de modelo |
| L3 | Turno «estado» de 71,7 s con ~60 s de espera entre dos pasos | Una llamada a Gemini quedó colgada; el timeout del cliente era de 90 s | Timeout de 30 s (reintento + respaldo) y middleware `RegistroLLM` que registra modelo, latencia y error de cada intento | E05: cada llamada 1–2 s, turno «estado» ~8 s |
| L4 | En una conversación nueva la burbuja del cliente desaparecía al enviar | Carrera en la interfaz: la carga del historial vacío pisaba el mensaje en curso | Si hay un mensaje pendiente no se carga el historial | Verificado en el navegador |
| L5 | `docker compose up` falla: «Bind for 0.0.0.0:8080 failed: port is already allocated» | Otra aplicación del equipo usa el 8080 | Puerto configurable `WEB_PORT`, por defecto 8088 | Stack arriba en :8088 |
| L6 | El hook PostToolUse del paquete original apuntaba a `verificar_flujo.py` (n8n), ya archivado | Cambio de plataforma: sin ese archivo, Python sale con código 2 y bloquea toda edición | Nuevo `scripts/verificar_codigo.py` (secretos, agentes sin acceso a la BD, umbral no escrito a mano, argumentos prohibidos en herramientas) | Detecta las 3 violaciones de un archivo de prueba y sale con 2 |
| L7 | Prueba `test_utilidad_reset…` fallaba | El teléfono de la prueba (`900001234` → `+51900001234`) también empieza con `+5190000` | Teléfono ficticio fuera del prefijo de pruebas | 47/47 |
