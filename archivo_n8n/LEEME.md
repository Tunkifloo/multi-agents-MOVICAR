# Archivo · versión n8n (solo referencia)

Material del paquete original pensado para desplegar la v3 en n8n. **Ya no se usa**: la solución se construyó con el ecosistema LangChain (ver `../README.md`). Se conserva para trazabilidad del diseño.

- `referencia/v2/`: los 4 flujos de la v2 multiagente de n8n.
- `workflows/LEEME.md`: convenciones de los flujos `sw_*` que la v3 iba a crear en n8n (hoy: `backend/app/servicios`).
- `scripts/n8n_deploy.py`, `scripts/n8n_cliente.py`: despliegue por la API de n8n y cliente del chat de n8n (reemplazado por `scripts/cliente_api.py`).
- `scripts/verificar_flujo.py`: controles sobre JSON de n8n (reemplazado por `scripts/verificar_codigo.py`).
- `config/n8n_ids.ejemplo.json`: IDs de Data Tables y flujos de n8n.
