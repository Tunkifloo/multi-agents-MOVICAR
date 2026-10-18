import { useEffect, useState } from "react";
import { ESTADOS, api, fechaCorta, hace, soles } from "../api";
import { Estado, Icono, Vacio } from "../componentes/ui";

function Detalle({ clave, cerrar }: { clave: string; cerrar: () => void }) {
  const [d, setD] = useState<any>(null);
  useEffect(() => { api.solicitud(clave).then(setD).catch(() => {}); }, [clave]);
  return (
    <aside className="cajon">
      <header>
        <div><strong>{d?.vehiculo ?? "…"}</strong> <span className="tenue">{d?.placa}</span></div>
        <button className="boton fantasma" onClick={cerrar} aria-label="Cerrar"><Icono n="cerrar" /></button>
      </header>
      {d && (
        <div className="cajon-cuerpo">
          <dl className="ficha">
            <dt>Estado</dt><dd><Estado e={d.estado} /></dd>
            <dt>Clave</dt><dd><code>{d.clave}</code></dd>
            <dt>Teléfono</dt><dd>{d.telefono}</dd>
            <dt>Descripción</dt><dd>{d.descripcion_falla}</dd>
            <dt>Agente</dt><dd>{d.tipo_servicio_agente} · confianza {Math.round(d.confianza_agente * 100)} %</dd>
            {d.tipo_servicio_jefe && <><dt>Jefe</dt><dd>{d.tipo_servicio_jefe} · {d.observacion_jefe}</dd></>}
            {d.motivo_revision && <><dt>Motivo revisión</dt><dd>{d.motivo_revision}</dd></>}
            <dt>Especialidad</dt><dd>{d.especialidad} · prioridad {d.prioridad}</dd>
            {d.turno_confirmado && <><dt>Cita</dt><dd>{fechaCorta(d.turno_confirmado.fecha)} {d.turno_confirmado.hora} · {d.turno_confirmado.mecanico}</dd></>}
          </dl>
          {d.cotizacion_detalle && (
            <>
              <h4>Cotización</h4>
              <table className="tabla compacta">
                <tbody>
                  {d.cotizacion_detalle.map((i: any) => (
                    <tr key={i.codigo}><td><code>{i.codigo}</code></td><td>{i.concepto}{i.bajo_pedido && <em className="aviso"> bajo pedido</em>}</td><td className="num">{i.cantidad}</td><td className="num">{soles(i.subtotal)}</td></tr>
                  ))}
                  <tr className="total"><td colSpan={3}>Total referencial</td><td className="num">{soles(d.total_cotizacion)}</td></tr>
                </tbody>
              </table>
            </>
          )}
          <h4>Trazas (historial de estados)</h4>
          <ol className="linea-tiempo">
            {d.historial.map((h: any) => (
              <li key={h.id}>
                <Estado e={h.estado_nuevo} />
                <span className="tenue pequeno">{h.actor} · {new Date(h.momento).toLocaleString("es-PE")}</span>
                {h.detalle && <code className="pequeno detalle-json">{h.detalle}</code>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </aside>
  );
}

export default function Solicitudes() {
  const [filas, setFilas] = useState<any[] | null>(null);
  const [filtro, setFiltro] = useState("");
  const [sel, setSel] = useState<string | null>(null);
  const [resumen, setResumen] = useState<any>(null);
  const cargar = () => {
    api.solicitudes(filtro || undefined).then(setFilas).catch(() => setFilas([]));
    api.resumen().then(setResumen).catch(() => {});
  };
  useEffect(cargar, [filtro]);

  return (
    <div className="pagina">
      <header className="pagina-cabecera">
        <div>
          <h1>Solicitudes</h1>
          <p className="tenue">Fuente de verdad del proceso. Cada cambio de estado lo hace la capa determinista y queda trazado.</p>
        </div>
        <button className="boton contorno" onClick={cargar}><Icono n="recargar" /> Actualizar</button>
      </header>
      <div className="filtros">
        <button className={`chip ${filtro === "" ? "activo" : ""}`} onClick={() => setFiltro("")}>Todas <b>{resumen?.total ?? ""}</b></button>
        {Object.entries(ESTADOS).map(([k, v]) => (
          <button key={k} className={`chip ${filtro === k ? "activo" : ""}`} onClick={() => setFiltro(k)}>
            {v.etiqueta} <b>{resumen?.por_estado?.[k] ?? 0}</b>
          </button>
        ))}
      </div>
      {filas === null ? <p className="tenue">Cargando…</p> : filas.length === 0 ? <Vacio titulo="Sin solicitudes" texto="Conversa con el asistente para crear la primera." /> : (
        <div className="tabla-envoltura">
          <table className="tabla">
            <thead><tr><th>Vehículo</th><th>Descripción</th><th>Tipo (agente)</th><th>Estado</th><th className="num">Total</th><th>Actualizado</th></tr></thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.clave} onClick={() => setSel(f.clave)} className="clicable">
                  <td><strong>{f.vehiculo}</strong><div className="tenue pequeno">{f.placa} · {fechaCorta(f.fecha_deseada)}</div></td>
                  <td className="recorte">{f.descripcion_falla}</td>
                  <td>{f.tipo_servicio_agente} <span className="tenue pequeno">{Math.round(f.confianza_agente * 100)} %</span></td>
                  <td><Estado e={f.estado} /></td>
                  <td className="num">{soles(f.total_cotizacion)}</td>
                  <td className="tenue pequeno">{hace(f.ts_estado)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {sel && <Detalle clave={sel} cerrar={() => setSel(null)} />}
    </div>
  );
}
