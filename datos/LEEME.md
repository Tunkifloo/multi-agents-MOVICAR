# Datos semilla

- **`catalogo_servicios_real_v2.csv`** (el que usa la aplicación): exportado de la Data Table real `movicar_catalogo_servicios` de la v2 en n8n (columnas `precio` y `horas`). El mantenimiento de 10 000 km da **S/ 355** (120 + 160 + 30 + 45), igual que en las pruebas de la v2 y en `tests/escenarios.json`. Se elige con `CATALOGO_CSV` en `.env`.
- `catalogo_servicios.csv`: catálogo de referencia del paquete original (precios calibrados, con `REP-DISCO`). Es un **elemento protegido** y se conserva sin cambios.
- La agenda **no** es un CSV: la genera `backend/app/db.py → asegurar_agenda()` desde la fecha de ejecución (lunes a sábado; 08:00, 11:00 y 15:00; Técnicos A, B y C) y el worker la extiende cada día. `scripts/generar_agenda.py` sigue disponible para exportarla a CSV.
- Todos los datos son ficticios (norma 4 de la guía del Lab 01). Los teléfonos de prueba empiezan con `+5190000`.
