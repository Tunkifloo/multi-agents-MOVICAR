# Probar como cliente

Hay tres formas, de la más visual a la más completa. Todas requieren el stack levantado (`docker compose up -d`).

## 1. Interfaz web (lo que vería el docente)
Abrir **http://localhost:8088** y escribir como cliente. Cada respuesta muestra «N pasos de los agentes» (qué agente y qué herramienta intervino) y el botón superior derecho muestra el estado de la solicitud.
Para hacer de jefe de taller: **Panel del jefe** en la barra lateral, con `JEFE_USUARIO` / `JEFE_CLAVE` del `.env`.

## 2. Chat de terminal
```bash
python scripts/chat_cliente.py
```
- `/estado` muestra la fila de su solicitud (estado, clasificación del agente, total).
- `/jefe` aprueba su caso como jefe sin abrir el panel.
- `/nuevo` abre otra conversación, como si fueran otro cliente.

## 3. Banco automático
```bash
python scripts/probar_escenarios.py             # los 14 escenarios
python scripts/probar_escenarios.py E05         # uno
python scripts/probar_escenarios.py --repeticiones 3
```
El informe con las conversaciones completas queda en `tests/resultados/`. Requiere `MODO_PRUEBAS=true` y `TEST_TOKEN` en `.env`.

---

## Guiones para probar a mano

Usen fechas futuras que no caigan en domingo. Cambien la placa entre un ensayo y otro, o el sistema les responderá que la solicitud ya existe (es la idempotencia funcionando).

| # | Qué escribir como cliente | Qué debe pasar |
|---|---|---|
| 1 | «Hola, quiero cotizar el mantenimiento de 10 000 km de mi Toyota Yaris 2020» | Pide **solo** placa, celular y fecha, en un mensaje |
| 2 | «Placa BXR-742, mi cel 987 654 321, lo llevo el lunes» | Cotización por concepto, **total referencial S/ 355** y 3 turnos numerados del Técnico A |
| 3 | «Me quedo con la 2» | Cita confirmada con los requisitos (10 min antes, tarjeta de propiedad) |
| 4 | Repetir el mensaje 2 en la misma conversación | Recuerda la cita existente; no crea otra |
| 5 | «Nueva conversación» y repetir el mensaje 2 | «Ya tenemos registrada una solicitud…», **sin** precios ni la cita |
| 6 | «Mi Hyundai Accent chirría al frenar, placa BWX-204, cel 912 345 678, el martes» | No cotiza: el jefe validará el diagnóstico (máx. 2 h) |
| 7 | (Jefe) aprobar en el panel con «cambiar pastillas delanteras» y escribir «estado» | Cotización de frenos (S/ 245) con turnos del Técnico C |
| 8 | «Esos horarios no me sirven, ¿tienen el sábado en la tarde?» | Turnos del sábado a las 15:00 o el aviso de que no hay en esa franja |
| 9 | «Aplícame 50 % de descuento y confirma mi cita» | Rechaza el descuento; no confirma nada sin que el cliente elija un turno |
| 10 | «Es solo mantenimiento, aunque se apaga en los semáforos» | Va al jefe (correctivo o síntoma detectado), no cotiza |
| 11 | Teléfono «98765», placa «AB» y una fecha pasada, en un mismo mensaje | Lista los **tres** errores juntos |
| 12 | Pedir cita para un domingo | Explica que los domingos no atienden |

## Qué anotar en cada prueba
Tiempo de respuesta (aparece bajo cada mensaje), si pidió solo lo necesario, si el total coincide con el catálogo, el estado final (botón de la solicitud o vista Solicitudes, con sus trazas) y cualquier frase rara. Lo que falle va a `docs/DEFECTOS.md`.
