import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AGENTES, Mensaje, Paso, api, enviarMensaje, fechaCorta, soles } from "../api";
import { Estado, Icono } from "../componentes/ui";

const SUGERENCIAS = [
  { t: "Mantenimiento de 10 000 km", m: "Hola, quiero cotizar el mantenimiento de 10 000 km de mi Toyota Yaris 2020." },
  { t: "Ruido al frenar", m: "Mi Hyundai Accent 2017 chirría al frenar y el pedal se siente esponjoso." },
  { t: "Cambio de aceite", m: "Necesito un cambio de aceite para mi Kia Rio 2019, ¿qué turnos tienen?" },
  { t: "¿Cómo va mi solicitud?", m: "estado" },
];

function Pasos({ pasos, vivo }: { pasos: Paso[]; vivo?: boolean }) {
  const [abierto, setAbierto] = useState(false);
  const utiles = pasos.filter((p) => p.accion !== "pensando");
  if (vivo) {
    const ultimo = pasos[pasos.length - 1];
    return (
      <div className="pasos-vivo" aria-live="polite">
        <span className="pulso" />
        <span><b>{AGENTES[ultimo?.agente] ?? "Orquestador"}</b> · {ultimo?.detalle ?? "Analizando tu mensaje"}</span>
      </div>
    );
  }
  if (!utiles.length) return null;
  return (
    <div className="pasos">
      <button className="pasos-boton" onClick={() => setAbierto(!abierto)} aria-expanded={abierto}>
        <span className={`giro ${abierto ? "abierto" : ""}`}><Icono n="chevron" t={14} /></span>
        {utiles.length} pasos de los agentes
      </button>
      {abierto && (
        <ol className="pasos-lista">
          {utiles.map((p, i) => (
            <li key={i} className={`agente-${p.agente}`}>
              <span className="pasos-agente">{AGENTES[p.agente] ?? p.agente}</span>
              <code>{p.accion}</code>
              <span className="tenue">{p.detalle}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function PanelSolicitud({ s, cerrar }: { s: any; cerrar: () => void }) {
  return (
    <aside className="panel-solicitud">
      <header>
        <strong>Tu solicitud</strong>
        <button className="boton fantasma" onClick={cerrar} aria-label="Cerrar"><Icono n="cerrar" /></button>
      </header>
      {!s?.existe ? <p className="tenue">Aún no hay una solicitud registrada en esta conversación.</p> : (
        <dl className="ficha">
          <dt>Estado</dt><dd><Estado e={s.estado} /></dd>
          <dt>Vehículo</dt><dd>{s.vehiculo} · {s.placa}</dd>
          <dt>Servicio</dt><dd>{s.tipo_servicio} · {s.especialidad?.replace("_", " ")}</dd>
          <dt>Fecha deseada</dt><dd>{fechaCorta(s.fecha_deseada)}</dd>
          {s.observacion_jefe && <><dt>Indicación del jefe</dt><dd>{s.observacion_jefe}</dd></>}
          {s.total_cotizacion != null && <><dt>Total referencial</dt><dd className="monto">{soles(s.total_cotizacion)}</dd></>}
          {s.requiere_proveedor && <><dt>Repuestos</dt><dd>Bajo pedido (confirmar con proveedor)</dd></>}
          {s.turno_confirmado && <><dt>Cita</dt><dd>{fechaCorta(s.turno_confirmado.fecha)}, {s.turno_confirmado.hora} · {s.turno_confirmado.mecanico}</dd></>}
          <dt>Código</dt><dd><code>{s.clave}</code></dd>
        </dl>
      )}
    </aside>
  );
}

export default function Chat({ sid, alCambiar, alNueva }: { sid?: string; alCambiar: () => void; alNueva: () => Promise<void> }) {
  const [mensajes, setMensajes] = useState<Mensaje[]>([]);
  const [texto, setTexto] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [pasosVivos, setPasosVivos] = useState<Paso[]>([]);
  const [solicitud, setSolicitud] = useState<any>(null);
  const [panel, setPanel] = useState(false);
  const fin = useRef<HTMLDivElement>(null);
  const entrada = useRef<HTMLTextAreaElement>(null);
  const pendiente = useRef<string | null>(null);

  useEffect(() => {
    setMensajes([]); setSolicitud(null); setPasosVivos([]);
    if (!sid) return;
    if (pendiente.current) {
      // conversación recién creada: no hay historial que cargar (evita pisar el mensaje en curso)
      const m = pendiente.current; pendiente.current = null;
      enviar(m, sid);
    } else {
      api.mensajes(sid).then(setMensajes).catch(() => {});
      api.solicitudDe(sid).then(setSolicitud).catch(() => {});
    }
    entrada.current?.focus();
  }, [sid]);

  useEffect(() => { fin.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [mensajes, pasosVivos]);

  const enviar = async (m: string, s = sid) => {
    const msg = m.trim();
    if (!msg || enviando) return;
    if (!s) { pendiente.current = msg; await alNueva(); return; }
    setTexto("");
    setEnviando(true);
    setPasosVivos([]);
    setMensajes((x) => [...x, { id: `c-${Date.now()}`, rol: "cliente", contenido: msg, pasos: [] }]);
    const acumulados: Paso[] = [];
    try {
      await enviarMensaje(s, msg, (ev) => {
        if (ev.tipo === "paso") { acumulados.push(ev); setPasosVivos([...acumulados]); }
        if (ev.tipo === "respuesta" || ev.tipo === "error") {
          setMensajes((x) => [...x, {
            id: `a-${Date.now()}`, rol: ev.tipo === "error" ? "error" : "asistente",
            contenido: ev.contenido, pasos: acumulados, segundos: ev.segundos,
          }]);
        }
      });
    } catch {
      setMensajes((x) => [...x, { id: `e-${Date.now()}`, rol: "error", contenido: "No se pudo conectar con el asistente. Revisa que el servicio esté levantado.", pasos: [] }]);
    } finally {
      setEnviando(false); setPasosVivos([]);
      alCambiar();
      api.solicitudDe(s).then(setSolicitud).catch(() => {});
      entrada.current?.focus();
    }
  };

  const vacio = mensajes.length === 0 && !enviando;

  return (
    <div className={`chat ${panel ? "con-panel" : ""}`}>
      <header className="chat-cabecera">
        <div className="chat-titulo">
          <strong>Asistente de cotizaciones y citas</strong>
          <span className="tenue pequeno">Orquestador + Agente Cotizador + Agente de Agenda</span>
        </div>
        {sid && (
          <button className="boton contorno" onClick={() => setPanel(!panel)}>
            <Icono n="auto" /> {solicitud?.existe ? <Estado e={solicitud.estado} /> : "Mi solicitud"}
          </button>
        )}
      </header>

      <div className="hilo">
        {vacio ? (
          <div className="bienvenida">
            <div className="bienvenida-logo">M</div>
            <h1>¿Qué necesita tu vehículo?</h1>
            <p className="tenue">Te cotizo mantenimiento o reparación con los precios del tarifario de MOVICAR y te reservo un turno con el técnico adecuado. Atendemos de lunes a sábado.</p>
            <div className="sugerencias">
              {SUGERENCIAS.map((s) => (
                <button key={s.t} className="sugerencia" onClick={() => enviar(s.m)}>
                  <strong>{s.t}</strong><span className="tenue">{s.m}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="mensajes">
            {mensajes.map((m) => (
              <div key={m.id} className={`mensaje ${m.rol}`}>
                {m.rol !== "cliente" && <div className="avatar">M</div>}
                <div className="cuerpo">
                  {m.rol === "cliente" ? <div className="burbuja-cliente">{m.contenido}</div> : (
                    <>
                      <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{m.contenido}</ReactMarkdown></div>
                      <div className="meta">
                        <Pasos pasos={m.pasos} />
                        {m.segundos != null && <span className="tenue pequeno"><Icono n="reloj" t={12} /> {m.segundos} s</span>}
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
            {enviando && (
              <div className="mensaje asistente">
                <div className="avatar latido">M</div>
                <div className="cuerpo"><Pasos pasos={pasosVivos} vivo /></div>
              </div>
            )}
            <div ref={fin} />
          </div>
        )}
      </div>

      <form className="compositor" onSubmit={(e) => { e.preventDefault(); enviar(texto); }}>
        <div className="compositor-caja">
          <textarea ref={entrada} value={texto} rows={1} placeholder="Escribe tu mensaje…" disabled={enviando}
            onChange={(e) => { setTexto(e.target.value); e.target.style.height = "auto"; e.target.style.height = Math.min(e.target.scrollHeight, 180) + "px"; }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(texto); } }} />
          <button className="boton enviar" disabled={enviando || !texto.trim()} aria-label="Enviar"><Icono n="enviar" /></button>
        </div>
        <p className="tenue pequeno centro">Las cotizaciones son referenciales y se confirman en el taller. Datos de prueba ficticios.</p>
      </form>

      {panel && <PanelSolicitud s={solicitud} cerrar={() => setPanel(false)} />}
    </div>
  );
}
