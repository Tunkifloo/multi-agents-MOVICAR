import { useCallback, useEffect, useState } from "react";
import { api, fechaCorta } from "../api";
import { Estado, Icono, Vacio } from "../componentes/ui";

function Caso({ c, alDecidir }: { c: any; alDecidir: () => void }) {
  const [tipo, setTipo] = useState(c.tipo_servicio_agente);
  const [prioridad, setPrioridad] = useState(c.prioridad);
  const [especialidad, setEspecialidad] = useState(c.especialidad);
  const [obs, setObs] = useState("");
  const [msg, setMsg] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const conf = Math.round(Number(c.confianza_agente) * 100);
  const slaPct = Math.min(100, (c.horas_en_estado / 2) * 100);

  const decidir = async (decision: "aprobar" | "rechazar") => {
    setOcupado(true); setMsg("");
    try {
      const r = await api.decidir({ clave: c.clave, decision, tipo_servicio: tipo, prioridad, especialidad, observacion: obs });
      if (r.ok) alDecidir(); else setMsg(r.mensaje || r.error);
    } catch (e: any) { setMsg(String(e.message || e)); } finally { setOcupado(false); }
  };

  return (
    <article className="tarjeta caso">
      <header className="caso-cabecera">
        <div>
          <h3>{c.vehiculo} <span className="tenue">· {c.placa}</span></h3>
          <span className="tenue pequeno">{c.telefono} · desea {fechaCorta(c.fecha_deseada)}{c.kilometraje ? ` · ${c.kilometraje.toLocaleString("es-PE")} km` : ""}</span>
        </div>
        <Estado e={c.estado} />
      </header>
      <blockquote className="caso-desc">«{c.descripcion_falla}»</blockquote>
      <div className="caso-ia">
        <div>
          <span className="etiqueta">Sugerencia del agente</span>
          <b>{c.tipo_servicio_agente}</b> · {c.especialidad.replace("_", " ")} · prioridad {c.prioridad}
        </div>
        <div className="confianza" title={`Confianza ${conf} %`}>
          <span className="etiqueta">Confianza {conf} %</span>
          <div className="barra"><i style={{ width: `${conf}%` }} className={conf < 90 ? "baja" : ""} /></div>
        </div>
        <div>
          <span className="etiqueta">Motivo de la revisión</span>{c.motivo_revision || "—"}
        </div>
        <div className={c.sla_vencido ? "sla vencido" : "sla"}>
          <span className="etiqueta"><Icono n="reloj" t={12} /> SLA 2 h · {c.horas_en_estado.toFixed(1)} h</span>
          <div className="barra"><i style={{ width: `${slaPct}%` }} /></div>
        </div>
      </div>
      <div className="caso-form">
        <label>Tipo<select value={tipo} onChange={(e) => setTipo(e.target.value)}><option>correctivo</option><option>preventivo</option></select></label>
        <label>Prioridad<select value={prioridad} onChange={(e) => setPrioridad(e.target.value)}><option>normal</option><option>alta</option></select></label>
        <label>Especialidad<select value={especialidad} onChange={(e) => setEspecialidad(e.target.value)}>
          <option value="general">general</option><option value="motor_electrico">motor y eléctrico</option><option value="frenos_suspension">frenos y suspensión</option>
        </select></label>
        <label className="ancho">Indicación técnica (obligatoria para aprobar)
          <textarea rows={2} value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Ej.: cambiar pastillas delanteras y purgar el líquido de frenos" />
        </label>
      </div>
      {msg && <div className="error-linea">{msg}</div>}
      <footer className="caso-acciones">
        <code className="tenue pequeno">{c.clave}</code>
        <button className="boton contorno" disabled={ocupado} onClick={() => decidir("rechazar")}>Rechazar</button>
        <button className="boton primario" disabled={ocupado || !obs.trim()} onClick={() => decidir("aprobar")}><Icono n="check" /> Aprobar diagnóstico</button>
      </footer>
    </article>
  );
}

export default function Jefe({ alCambiar }: { alCambiar: () => void }) {
  const [casos, setCasos] = useState<any[] | null>(null);
  const [met, setMet] = useState<any>(null);
  const cargar = useCallback(() => {
    api.pendientes().then(setCasos).catch(() => setCasos([]));
    api.metricas().then(setMet).catch(() => {});
    alCambiar();
  }, [alCambiar]);
  useEffect(() => { cargar(); const t = setInterval(cargar, 15000); return () => clearInterval(t); }, [cargar]);

  return (
    <div className="pagina">
      <header className="pagina-cabecera">
        <div>
          <h1>Panel del jefe de taller</h1>
          <p className="tenue">Casos que la compuerta de riesgo envió a revisión: correctivos o con confianza del agente menor a 0,90. El cliente recibe su cotización cuando vuelve a escribir.</p>
        </div>
        <button className="boton contorno" onClick={cargar}><Icono n="recargar" /> Actualizar</button>
      </header>
      {met && (
        <section className="kpis">
          <div className="kpi"><span>Pendientes</span><b>{casos?.length ?? "—"}</b></div>
          <div className="kpi"><span>Decididos por el jefe</span><b>{met.casos_decididos}</b></div>
          <div className="kpi"><span>Acuerdo agente-jefe</span><b>{met.acuerdo == null ? "—" : `${Math.round(met.acuerdo * 100)} %`}</b></div>
          <div className="kpi"><span>Puerta de calibración</span><b className={met.aprueba_puerta ? "ok" : ""}>{met.aprueba_puerta ? "Aprueba" : "≥ 30 casos y ≥ 90 %"}</b></div>
        </section>
      )}
      {casos === null ? <p className="tenue">Cargando…</p> : casos.length === 0
        ? <Vacio icono="jefe" titulo="No hay casos pendientes" texto="Cuando un cliente describa una falla, aparecerá aquí para validar el diagnóstico." />
        : <div className="casos">{casos.map((c) => <Caso key={c.clave} c={c} alDecidir={cargar} />)}</div>}
    </div>
  );
}
