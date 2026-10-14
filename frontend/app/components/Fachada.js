import { clp } from "../../lib/api";

export function estadoUnidad(u) {
  if (u.vencida > 0) return "persiana";            // deuda vencida: persiana baja
  if (u.visitas_activas > 0) return "encendida";   // visita en el edificio: ventana encendida
  if (!u.residentes.length) return "vacia";
  return "clara";
}

export function pisoDe(numero) {
  const m = String(numero).match(/^(\d+?)(\d{2})$/);
  return m ? parseInt(m[1], 10) : 1;
}

export default function Fachada({ data, filtro, seleccionada, onSelect }) {
  const pisos = new Map();
  data.unidades.forEach((u) => {
    const p = pisoDe(u.numero);
    if (!pisos.has(p)) pisos.set(p, []);
    pisos.get(p).push(u);
  });
  const orden = [...pisos.keys()].sort((a, b) => b - a);
  const cols = Math.max(...[...pisos.values()].map((x) => x.length));
  const ed = data.edificio;
  const libres = ed.cupos_visitas - ed.cupos_ocupados;
  return (
    <div className="fachada-wrap">
      <div className="fachada" style={{ "--cols": cols }} role="grid" aria-label={`Fachada de ${ed.nombre}`}>
        <div className="cornisa" aria-hidden="true" />
        {orden.map((p) => (
          <div className="piso" role="row" key={p}>
            <span className="piso-n" aria-hidden="true">{p}</span>
            {pisos.get(p).sort((a, b) => a.numero.localeCompare(b.numero)).map((u) => {
              const est = estadoUnidad(u);
              const apagada = filtro && filtro !== est;
              return (
                <button key={u.id} role="gridcell" className={`ventana ${est} ${apagada ? "apagada" : ""} ${seleccionada === u.id ? "sel" : ""}`}
                  onClick={() => onSelect(u.id)}
                  aria-label={`Departamento ${u.numero}: ${est === "persiana" ? "deuda vencida " + clp(u.vencida) : est === "encendida" ? "visita en el edificio" : est === "vacia" ? "sin residentes" : "al día"}`}>
                  <span className="num">{u.numero}</span>
                  {u.vehiculos.length > 0 && <span className="autos" aria-hidden="true">{"▪".repeat(u.vehiculos.length)}</span>}
                </button>
              );
            })}
          </div>
        ))}
        <div className="zocalo" aria-label="Portón y estacionamientos de visitas">
          <div className="porton" aria-hidden="true"><span /><span /></div>
          <div className="bahias" title={`${libres} de ${ed.cupos_visitas} cupos de visita libres`}>
            {Array.from({ length: ed.cupos_visitas }, (_, i) => (
              <span key={i} className={i < ed.cupos_ocupados ? "bahia ocupada" : "bahia"} />
            ))}
            <em>{libres} de {ed.cupos_visitas} cupos libres</em>
          </div>
        </div>
      </div>
      <ul className="leyenda">
        {[["clara", "Al día"], ["persiana", "Deuda vencida"], ["encendida", "Visita adentro"], ["vacia", "Sin residentes"]].map(([k, t]) => (
          <li key={k}><i className={`ventana-mini ${k}`} />{t}</li>
        ))}
      </ul>
    </div>
  );
}
