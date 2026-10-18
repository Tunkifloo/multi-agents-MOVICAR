import { useEffect, useMemo, useState } from "react";
import { api, fechaCorta } from "../api";
import { Icono } from "../componentes/ui";

const hoyLima = () => new Date(Date.now() - 5 * 3600 * 1000).toISOString().slice(0, 10);
const sumar = (iso: string, n: number) => {
  const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10);
};
const TECNICOS = [
  { m: "Técnico A", e: "General" }, { m: "Técnico B", e: "Motor y eléctrico" }, { m: "Técnico C", e: "Frenos y suspensión" },
];

export default function Agenda() {
  const [desde, setDesde] = useState(hoyLima());
  const [turnos, setTurnos] = useState<any[]>([]);
  useEffect(() => { api.agenda(desde, 7).then(setTurnos).catch(() => setTurnos([])); }, [desde]);

  const dias = useMemo(() => [...new Set(turnos.map((t) => t.fecha))], [turnos]);
  const horas = ["08:00", "11:00", "15:00"];
  const celda = (f: string, h: string, m: string) => turnos.find((t) => t.fecha === f && t.hora === h && t.mecanico === m);
  const ocupados = turnos.filter((t) => t.estado === "reservado").length;

  return (
    <div className="pagina">
      <header className="pagina-cabecera">
        <div>
          <h1>Agenda de turnos</h1>
          <p className="tenue">Lunes a sábado, 08:00 · 11:00 · 15:00. Se genera sola desde hoy (no caduca). Ocupación de la semana: {turnos.length ? Math.round((ocupados / turnos.length) * 100) : 0} %.</p>
        </div>
        <div className="grupo">
          <button className="boton contorno" onClick={() => setDesde(sumar(desde, -7))} aria-label="Semana anterior">‹</button>
          <button className="boton contorno" onClick={() => setDesde(hoyLima())}>Hoy</button>
          <button className="boton contorno" onClick={() => setDesde(sumar(desde, 7))} aria-label="Semana siguiente">›</button>
        </div>
      </header>
      <div className="leyenda">
        <span><i className="punto libre" /> Libre</span><span><i className="punto reservado" /> Reservado</span><span><i className="punto prueba" /> Ocupado en pruebas</span>
      </div>
      <div className="tabla-envoltura">
        <table className="agenda">
          <thead>
            <tr><th>Técnico</th><th>Hora</th>{dias.map((d) => <th key={d}>{fechaCorta(d)}</th>)}</tr>
          </thead>
          <tbody>
            {TECNICOS.map((t) => horas.map((h, i) => (
              <tr key={t.m + h} className={i === 0 ? "grupo-inicio" : ""}>
                {i === 0 && <th rowSpan={3} className="tecnico"><Icono n="auto" t={14} /> {t.m}<span className="tenue pequeno">{t.e}</span></th>}
                <td className="tenue pequeno">{h}</td>
                {dias.map((d) => {
                  const c = celda(d, h, t.m);
                  const clase = !c ? "nada" : c.estado === "libre" ? "libre" : c.clave_solicitud === "TEST-OCUPADO" ? "prueba" : "reservado";
                  return <td key={d} className={`turno ${clase}`} title={c?.clave_solicitud ?? c?.turno_id}>{c ? (c.estado === "libre" ? "" : (c.clave_solicitud ?? "reservado").slice(0, 10)) : "—"}</td>;
                })}
              </tr>
            )))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
