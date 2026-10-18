// Cliente del API de MOVICAR. Las credenciales del personal viven solo en sessionStorage.

export type Paso = { tipo: "paso"; agente: string; accion: string; detalle: string };
export type EventoChat =
  | Paso
  | { tipo: "respuesta"; contenido: string; segundos: number; pasos: Paso[] }
  | { tipo: "error"; contenido: string; clase_error: string; segundos: number }
  | { tipo: "fin" };

export type Mensaje = {
  id: number | string;
  rol: "cliente" | "asistente" | "error";
  contenido: string;
  pasos: Paso[];
  segundos?: number | null;
};
export type Conversacion = { session_id: string; titulo: string; actualizado_en?: string };

const CLAVE_AUTH = "movicar.auth";

export const auth = {
  get: () => {
    try { return sessionStorage.getItem(CLAVE_AUTH); } catch { return null; }
  },
  set: (usuario: string, clave: string) => {
    const v = "Basic " + btoa(unescape(encodeURIComponent(`${usuario}:${clave}`)));
    try { sessionStorage.setItem(CLAVE_AUTH, v); } catch { /* sin almacenamiento */ }
    return v;
  },
  borrar: () => { try { sessionStorage.removeItem(CLAVE_AUTH); } catch { /* */ } },
};

export class NoAutorizado extends Error {}

async function pedir<T>(ruta: string, init: RequestInit = {}, conAuth = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json", ...(init.headers as any) };
  if (conAuth) {
    const a = auth.get();
    if (a) headers.Authorization = a;
  }
  const r = await fetch(`/api${ruta}`, { ...init, headers });
  if (r.status === 401) throw new NoAutorizado();
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  salud: () => pedir<any>("/salud"),
  conversaciones: () => pedir<Conversacion[]>("/conversaciones"),
  nuevaConversacion: () => pedir<Conversacion>("/conversaciones", { method: "POST" }),
  mensajes: (sid: string) => pedir<Mensaje[]>(`/conversaciones/${sid}/mensajes`),
  solicitudDe: (sid: string) => pedir<any>(`/conversaciones/${sid}/solicitud`),
  verificar: () => pedir<any>("/auth/verificar", {}, true),
  pendientes: () => pedir<any[]>("/jefe/pendientes", {}, true),
  decidir: (d: any) => pedir<any>("/jefe/decision", { method: "POST", body: JSON.stringify(d) }, true),
  metricas: () => pedir<any>("/jefe/metricas", {}, true),
  resumen: () => pedir<any>("/resumen", {}, true),
  solicitudes: (estado?: string) => pedir<any[]>(`/solicitudes${estado ? `?estado=${estado}` : ""}`, {}, true),
  solicitud: (clave: string) => pedir<any>(`/solicitudes/${clave}`, {}, true),
  agenda: (desde: string, dias = 6) => pedir<any[]>(`/agenda?desde=${desde}&dias=${dias}`, {}, true),
  catalogo: () => pedir<any[]>("/catalogo", {}, true),
  fallos: () => pedir<any[]>("/fallos", {}, true),
  programados: () => pedir<any>("/programados/ejecutar", { method: "POST" }, true),
};

/** Envía un mensaje y va entregando los eventos SSE (pasos de los agentes y respuesta final). */
export async function enviarMensaje(sid: string, mensaje: string, alEvento: (e: EventoChat) => void) {
  const r = await fetch(`/api/chat/${sid}/stream`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mensaje }),
  });
  if (!r.ok || !r.body) throw new Error(`Error ${r.status}`);
  const lector = r.body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await lector.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    let i;
    while ((i = buffer.indexOf("\n\n")) >= 0) {
      const bloque = buffer.slice(0, i);
      buffer = buffer.slice(i + 2);
      const linea = bloque.split("\n").find((l) => l.startsWith("data: "));
      if (linea) alEvento(JSON.parse(linea.slice(6)));
    }
  }
}

export const ESTADOS: Record<string, { etiqueta: string; tono: string }> = {
  revision_jefe: { etiqueta: "En revisión del jefe", tono: "ambar" },
  escalada_recepcion: { etiqueta: "Escalada a Recepción", tono: "rojo" },
  lista_para_cotizar: { etiqueta: "Lista para cotizar", tono: "azul" },
  validada_jefe: { etiqueta: "Validada por el jefe", tono: "azul" },
  cotizada: { etiqueta: "Cotizada", tono: "violeta" },
  sin_confirmar_seguimiento: { etiqueta: "Sin confirmar (48 h)", tono: "ambar" },
  agendada: { etiqueta: "Cita agendada", tono: "verde" },
  rechazada: { etiqueta: "Cerrada", tono: "gris" },
};

export const AGENTES: Record<string, string> = {
  orquestador: "Orquestador",
  cotizador: "Agente Cotizador",
  agenda: "Agente de Agenda",
};

export const soles = (n: number | null | undefined) =>
  n == null ? "—" : `S/ ${Number(n).toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
export const fechaCorta = (iso: string) => {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  const f = new Date(y, m - 1, d);
  return `${DIAS[f.getDay()]} ${d} ${MESES[m - 1]}`;
};
export const hace = (iso?: string) => {
  if (!iso) return "";
  const min = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (min < 1) return "ahora";
  if (min < 60) return `hace ${min} min`;
  const h = Math.round(min / 60);
  return h < 24 ? `hace ${h} h` : `hace ${Math.round(h / 24)} d`;
};
