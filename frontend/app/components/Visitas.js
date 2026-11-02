import { useEffect, useState } from "react";
import Placa from "./Placa";

const hm = (iso) => new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" });
const ETQ = { reservada: "Esperando", llego: "Adentro", no_show: "No llegó, cupo liberado", cancelada: "Cancelada" };

export default function Visitas({ visitas, data, api }) {
  const ed = data.edificio;
  const [abierto, setAbierto] = useState(null); // { id, url } del QR que se está mostrando
  const [error, setError] = useState("");
  useEffect(() => () => { if (abierto?.url?.startsWith("blob:")) URL.revokeObjectURL(abierto.url); }, [abierto]);
  const verQr = async (v) => {
    if (abierto?.id === v.id) { setAbierto(null); return; }
    setError("");
    try { setAbierto({ id: v.id, url: await api.qrVisita(v.id) }); }
    catch { setError("No se pudo cargar el QR. Intente de nuevo."); }
  };
  return (
    <div className="visitas-vista">
      <header className="vista-cab">
        <h2>Visitas</h2>
        <p>{ed.cupos_visitas - ed.cupos_ocupados} de {ed.cupos_visitas} cupos de visita libres ahora. Una reserva se libera sola si la visita no llega dentro de la tolerancia.</p>
      </header>
      {visitas.length === 0 && <p className="vacio">No hay visitas reservadas para hoy.</p>}
      {error && <p role="alert" className="aviso err">{error}</p>}
      <ul className="visitas">
        {visitas.map((v) => (
          <li key={v.id} className={`v-${v.estado}`}>
            <span className="v-depto">{v.unidad}</span>
            <div><b>{v.nombre}</b><span>{hm(v.desde)} a {hm(v.hasta)} · {ETQ[v.estado] || v.estado}</span></div>
            {v.usa_estacionamiento ? (v.patente ? <Placa valor={v.patente} pequena /> : <span className="sin-pat">Estaciona, sin patente</span>) : <span className="sin-pat">A pie</span>}
            {api && (v.estado === "reservada" || v.estado === "llego") && (
              <button className="mini" onClick={() => verQr(v)} aria-expanded={abierto?.id === v.id}>{abierto?.id === v.id ? "Ocultar QR" : "Ver QR"}</button>)}
            {abierto?.id === v.id && <img className="qr-en-lista" src={abierto.url} alt={`Código QR de ${v.nombre}`} width={140} height={140} />}
          </li>
        ))}
      </ul>
    </div>
  );
}
