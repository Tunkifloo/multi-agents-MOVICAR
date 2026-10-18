import { ReactNode, useState } from "react";
import { ESTADOS, api, auth } from "../api";

const trazos: Record<string, ReactNode> = {
  plus: <path d="M12 5v14M5 12h14" />,
  chat: <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />,
  jefe: <><path d="M12 3 4 6v6c0 5 3.4 8.3 8 9 4.6-.7 8-4 8-9V6l-8-3Z" /><path d="m9 12 2 2 4-4" /></>,
  lista: <><path d="M8 6h13M8 12h13M8 18h13" /><path d="M3.5 6h.01M3.5 12h.01M3.5 18h.01" /></>,
  agenda: <><rect x="3" y="4.5" width="18" height="16" rx="2" /><path d="M3 9.5h18M8 3v3M16 3v3" /></>,
  alerta: <><path d="M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /><path d="M12 9v4M12 17h.01" /></>,
  enviar: <path d="M5 12h14M13 6l6 6-6 6" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  sol: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></>,
  luna: <path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5Z" />,
  salir: <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H4" />,
  cerrar: <path d="M6 6l12 12M18 6 6 18" />,
  chevron: <path d="m9 6 6 6-6 6" />,
  llave: <><circle cx="8" cy="15" r="4" /><path d="m10.8 12.2 9.2-9.2M17 6l3 3M14 9l2 2" /></>,
  recargar: <path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7" />,
  auto: <><path d="M5 17h14v-5l-2-5H7l-2 5v5Z" /><circle cx="8" cy="17" r="2" /><circle cx="16" cy="17" r="2" /><path d="M5 12h14" /></>,
  reloj: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
  check: <path d="m5 12 5 5 9-10" />,
};

export function Icono({ n, t = 18 }: { n: keyof typeof trazos | string; t?: number }) {
  return (
    <svg width={t} height={t} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8}
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{trazos[n]}</svg>
  );
}

export function Estado({ e }: { e?: string }) {
  if (!e) return null;
  const d = ESTADOS[e] ?? { etiqueta: e, tono: "gris" };
  return <span className={`insignia tono-${d.tono}`}>{d.etiqueta}</span>;
}

export function Vacio({ titulo, texto, icono = "lista" }: { titulo: string; texto?: string; icono?: string }) {
  return (
    <div className="vacio">
      <Icono n={icono} t={28} />
      <strong>{titulo}</strong>
      {texto && <p>{texto}</p>}
    </div>
  );
}

/** Formulario de acceso del personal del taller (Basic Auth contra el API). */
export function Acceso({ alEntrar }: { alEntrar: () => void }) {
  const [usuario, setUsuario] = useState("jefe");
  const [clave, setClave] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);
  const entrar = async (ev: React.FormEvent) => {
    ev.preventDefault();
    setCargando(true); setError("");
    auth.set(usuario, clave);
    try {
      await api.verificar();
      alEntrar();
    } catch {
      auth.borrar();
      setError("Usuario o clave incorrectos.");
    } finally { setCargando(false); }
  };
  return (
    <div className="acceso">
      <form className="tarjeta acceso-caja" onSubmit={entrar}>
        <div className="acceso-icono"><Icono n="llave" t={22} /></div>
        <h2>Acceso del personal</h2>
        <p className="tenue">El panel del jefe de taller y el back-office requieren credenciales (definidas en <code>.env</code>).</p>
        <label>Usuario<input value={usuario} onChange={(e) => setUsuario(e.target.value)} autoComplete="username" /></label>
        <label>Clave<input type="password" value={clave} onChange={(e) => setClave(e.target.value)} autoComplete="current-password" autoFocus /></label>
        {error && <div className="error-linea">{error}</div>}
        <button className="boton primario" disabled={cargando || !clave}>{cargando ? "Verificando…" : "Entrar"}</button>
      </form>
    </div>
  );
}
