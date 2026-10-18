import { useEffect, useState } from "react";
import { api } from "../api";
import { Icono, Vacio } from "../componentes/ui";

export default function Fallos() {
  const [filas, setFilas] = useState<any[] | null>(null);
  const [prog, setProg] = useState<any>(null);
  const cargar = () => api.fallos().then(setFilas).catch(() => setFilas([]));
  useEffect(() => { cargar(); }, []);
  const correr = async () => { setProg(await api.programados()); cargar(); };

  return (
    <div className="pagina">
      <header className="pagina-cabecera">
        <div>
          <h1>Cola de fallidos</h1>
          <p className="tenue">Fallos técnicos tras 3 reintentos con respaldo de modelo. Clases: transitorio (cuota, red), de datos (validación) y de sistema (credenciales, modelo, desconocido).</p>
        </div>
        <div className="grupo">
          <button className="boton contorno" onClick={correr} title="Ejecuta ahora el SLA de 2 h y el seguimiento de 48 h"><Icono n="reloj" /> Ejecutar programados</button>
          <button className="boton contorno" onClick={cargar}><Icono n="recargar" /> Actualizar</button>
        </div>
      </header>
      {prog && <div className="aviso-linea">Programados: {prog.escaladas.length} escaladas a Recepción · {prog.seguimiento.length} pasadas a seguimiento 48 h · {prog.turnos_creados} turnos nuevos en agenda.</div>}
      {filas === null ? <p className="tenue">Cargando…</p> : filas.length === 0 ? <Vacio icono="check" titulo="Sin fallos registrados" texto="Todo en orden." /> : (
        <div className="tabla-envoltura">
          <table className="tabla">
            <thead><tr><th>Momento</th><th>Flujo</th><th>Clase</th><th>Motivo</th><th className="num">Intentos</th></tr></thead>
            <tbody>
              {filas.map((f) => (
                <tr key={f.id}>
                  <td className="pequeno">{new Date(f.momento).toLocaleString("es-PE")}</td>
                  <td>{f.flujo}<div className="tenue pequeno"><code>{f.ejecucion}</code></div></td>
                  <td><span className={`insignia tono-${f.clase_error === "transitorio" ? "ambar" : f.clase_error === "de_datos" ? "azul" : "rojo"}`}>{f.clase_error}</span></td>
                  <td className="recorte largo" title={f.motivo}>{f.motivo}</td>
                  <td className="num">{f.intentos}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
