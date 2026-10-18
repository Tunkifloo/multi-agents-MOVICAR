"""chat_cliente.py · Habla con el asistente de MOVICAR como si fueras un cliente.

Uso: python scripts/chat_cliente.py
Comandos:  /nuevo   nueva conversación (otra sesión, como otro cliente)
           /estado  muestra la fila de tu solicitud en movicar_solicitudes (requiere la utilidad de pruebas)
           /jefe    aprueba tu caso como jefe de taller (requiere la utilidad de pruebas)
           /salir
"""
import sys, uuid
sys.path.insert(0, __import__("os").path.dirname(__file__))
from cliente_api import cargar_env, enviar_mensaje, utilidad

def main():
    cargar_env()
    sesion = "cli-" + uuid.uuid4().hex[:10]
    print(f"MOVICAR · chat de prueba (sesión {sesion}). Escribe como cliente. /nuevo /estado /jefe /salir\n")
    while True:
        try:
            msg = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        if msg == "/salir":
            break
        if msg == "/nuevo":
            sesion = "cli-" + uuid.uuid4().hex[:10]; print(f"— nueva sesión {sesion} —\n"); continue
        if msg == "/estado":
            fila = utilidad("get_solicitud", session_id=sesion)
            for k in ("clave", "estado", "tipo_servicio_agente", "confianza_agente", "especialidad", "total_cotizacion", "turno_confirmado"):
                print(f"   {k}: {fila.get(k)}") if isinstance(fila, dict) else None
            print(); continue
        if msg == "/jefe":
            fila = utilidad("get_solicitud", session_id=sesion)
            obs = input("   Indicación del jefe: ") or "Revisar y cotizar según síntoma"
            esp = input("   Especialidad [frenos_suspension/motor_electrico/general]: ") or fila.get("especialidad", "general")
            print("  ", utilidad("aprobar_jefe", clave=fila.get("clave"), tipo_servicio="correctivo", prioridad="alta", especialidad=esp, observacion=obs), "\n")
            continue
        resp, seg = enviar_mensaje(sesion, msg)
        print(f"\nMOVICAR ({seg}s): {resp}\n")

if __name__ == "__main__":
    main()
