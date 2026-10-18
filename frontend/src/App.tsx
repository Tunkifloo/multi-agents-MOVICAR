import { useCallback, useEffect, useState } from "react";
import { Conversacion, NoAutorizado, api, auth, hace } from "./api";
import { Acceso, Icono } from "./componentes/ui";
import Chat from "./vistas/Chat";
import Jefe from "./vistas/Jefe";
import Solicitudes from "./vistas/Solicitudes";
import Agenda from "./vistas/Agenda";
import Fallos from "./vistas/Fallos";

type Ruta = { vista: "chat"; sid?: string } | { vista: "jefe" | "solicitudes" | "agenda" | "fallos" };

function leerRuta(): Ruta {
  const [, vista, sid] = location.hash.replace(/^#/, "").split("/");
  if (vista === "jefe" || vista === "solicitudes" || vista === "agenda" || vista === "fallos") return { vista };
  return { vista: "chat", sid: sid || undefined };
}

function temaInicial(): "claro" | "oscuro" {
  try {
    const t = localStorage.getItem("movicar.tema");
    if (t === "claro" || t === "oscuro") return t;
  } catch { /* */ }
  return matchMedia("(prefers-color-scheme: dark)").matches ? "oscuro" : "claro";
}

export default function App() {
  const [ruta, setRuta] = useState<Ruta>(leerRuta);
  const [convs, setConvs] = useState<Conversacion[]>([]);
  const [tema, setTema] = useState(temaInicial);
  const [personal, setPersonal] = useState(!!auth.get());
  const [pendientes, setPendientes] = useState<number | null>(null);
  const [menuAbierto, setMenuAbierto] = useState(false);

  useEffect(() => {
    const f = () => { setRuta(leerRuta()); setMenuAbierto(false); };
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = tema === "oscuro" ? "dark" : "light";
    try { localStorage.setItem("movicar.tema", tema); } catch { /* */ }
  }, [tema]);

  const cargarConvs = useCallback(() => api.conversaciones().then(setConvs).catch(() => {}), []);
  useEffect(() => { cargarConvs(); }, [cargarConvs]);

  const cargarPendientes = useCallback(() => {
    if (!auth.get()) return;
    api.resumen().then((r) => setPendientes(r.pendientes_jefe)).catch((e) => {
      if (e instanceof NoAutorizado) { auth.borrar(); setPersonal(false); }
    });
  }, []);
  useEffect(() => {
    cargarPendientes();
    const t = setInterval(cargarPendientes, 20000);
    return () => clearInterval(t);
  }, [cargarPendientes, personal]);

  const nueva = async () => {
    const c = await api.nuevaConversacion();
    await cargarConvs();
    location.hash = `#/chat/${c.session_id}`;
  };

  const salir = () => { auth.borrar(); setPersonal(false); setPendientes(null); location.hash = "#/chat"; };
  const enlace = (v: string, icono: string, texto: string, extra?: React.ReactNode) => (
    <a href={`#/${v}`} className={`nav-item ${ruta.vista === v ? "activo" : ""}`}>
      <Icono n={icono} /> <span>{texto}</span> {extra}
    </a>
  );
  const vistaPersonal = ruta.vista !== "chat";

  return (
    <div className={`app ${menuAbierto ? "menu-abierto" : ""}`}>
      <aside className="lateral">
        <div className="marca">
          <div className="marca-logo">M</div>
          <div>
            <strong>MOVICAR</strong>
            <span>Taller Mecánico · Trujillo</span>
          </div>
        </div>
        <button className="boton nueva" onClick={nueva}><Icono n="plus" /> Nueva conversación</button>

        <div className="lateral-seccion">Conversaciones</div>
        <nav className="convs">
          {convs.length === 0 && <div className="tenue pequeno pad">Aún no hay conversaciones.</div>}
          {convs.map((c) => (
            <a key={c.session_id} href={`#/chat/${c.session_id}`}
              className={`conv ${ruta.vista === "chat" && ruta.sid === c.session_id ? "activo" : ""}`}>
              <span className="conv-titulo">{c.titulo}</span>
              <span className="conv-hora">{hace(c.actualizado_en)}</span>
            </a>
          ))}
        </nav>

        <div className="lateral-seccion">Taller</div>
        <nav className="nav">
          {enlace("jefe", "jefe", "Panel del jefe", pendientes ? <b className="burbuja">{pendientes}</b> : null)}
          {enlace("solicitudes", "lista", "Solicitudes")}
          {enlace("agenda", "agenda", "Agenda")}
          {enlace("fallos", "alerta", "Cola de fallidos")}
        </nav>

        <div className="lateral-pie">
          <button className="boton fantasma" onClick={() => setTema(tema === "oscuro" ? "claro" : "oscuro")}
            title="Cambiar tema" aria-label="Cambiar tema">
            <Icono n={tema === "oscuro" ? "sol" : "luna"} />
          </button>
          {personal && <button className="boton fantasma" onClick={salir} title="Cerrar sesión del personal"><Icono n="salir" /> Salir</button>}
          <span className="tenue pequeno">LangChain · LangGraph · Gemini</span>
        </div>
      </aside>
      <div className="velo" onClick={() => setMenuAbierto(false)} />

      <main className="principal">
        <button className="boton fantasma boton-menu" onClick={() => setMenuAbierto(true)} aria-label="Abrir menú"><Icono n="menu" /></button>
        {ruta.vista === "chat" && <Chat sid={ruta.sid} alCambiar={cargarConvs} alNueva={nueva} />}
        {vistaPersonal && !personal && <Acceso alEntrar={() => { setPersonal(true); cargarPendientes(); }} />}
        {vistaPersonal && personal && ruta.vista === "jefe" && <Jefe alCambiar={cargarPendientes} />}
        {vistaPersonal && personal && ruta.vista === "solicitudes" && <Solicitudes />}
        {vistaPersonal && personal && ruta.vista === "agenda" && <Agenda />}
        {vistaPersonal && personal && ruta.vista === "fallos" && <Fallos />}
      </main>
    </div>
  );
}
