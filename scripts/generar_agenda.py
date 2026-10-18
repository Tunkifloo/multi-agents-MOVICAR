"""Genera la agenda de turnos relativa a hoy (zona America/Lima).

Uso:  python scripts/generar_agenda.py --dias 21 [--desde 2026-10-19] > datos/agenda_turnos.csv
Lunes a sábado, 08:00 / 11:00 / 15:00, tres técnicos (uno por especialidad). Domingos excluidos.
"""
import argparse, csv, sys
from datetime import date, datetime, timedelta, timezone

TECNICOS = [("A", "Técnico A", "general"), ("B", "Técnico B", "motor_electrico"), ("C", "Técnico C", "frenos_suspension")]
HORAS = ["08:00", "11:00", "15:00"]

def hoy_lima() -> date:
    return (datetime.now(timezone.utc) - timedelta(hours=5)).date()

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--dias", type=int, default=21)
    p.add_argument("--desde", type=lambda s: date.fromisoformat(s), default=None)
    a = p.parse_args()
    inicio = a.desde or hoy_lima()
    w = csv.writer(sys.stdout, lineterminator="\n")
    w.writerow(["turno_id", "fecha", "hora", "franja", "mecanico", "especialidad", "estado", "clave_solicitud"])
    for d in range(a.dias):
        dia = inicio + timedelta(days=d)
        if dia.weekday() == 6:  # domingo
            continue
        for hora in HORAS:
            for letra, nombre, esp in TECNICOS:
                tid = f"T-{dia:%m%d}-{hora[:2]}-{letra}"
                franja = "manana" if int(hora[:2]) < 12 else "tarde"
                w.writerow([tid, dia.isoformat(), hora, franja, nombre, esp, "libre", ""])

if __name__ == "__main__":
    main()
