"""metricas_acuerdo.py · Acuerdo entre la clasificación del agente y la del jefe de taller (puerta 3).

Uso: python scripts/metricas_acuerdo.py   (usa la acción «listar» de la utilidad de pruebas)
Umbral de aprobación de la puerta: ≥ 30 casos decididos por el jefe y acuerdo ≥ 90 %.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cliente_api import cargar_env, utilidad

def main():
    cargar_env()
    filas = utilidad("listar").get("filas", [])
    dec = [f for f in filas if f.get("tipo_servicio_jefe")]
    if not dec:
        print("Aún no hay casos decididos por el jefe."); return
    acuerdo = sum(f["tipo_servicio_agente"] == f["tipo_servicio_jefe"] for f in dec)
    print(f"Casos decididos por el jefe: {len(dec)}")
    print(f"Acuerdo en tipo de servicio: {acuerdo}/{len(dec)} = {acuerdo / len(dec):.0%}")
    for f in dec:
        if f["tipo_servicio_agente"] != f["tipo_servicio_jefe"]:
            print(f"  desacuerdo {f['clave']}: agente={f['tipo_servicio_agente']} ({f.get('confianza_agente')}) jefe={f['tipo_servicio_jefe']} · {f.get('descripcion_falla','')[:60]}")
    estado = "APRUEBA" if len(dec) >= 30 and acuerdo / len(dec) >= 0.9 else "NO APRUEBA (todavía)"
    print(f"Puerta 3: {estado}")

if __name__ == "__main__":
    main()
