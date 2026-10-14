import Placa from "./Placa";

const hora = (iso) => new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const esPatente = (t) => /^[A-Z]{2}[A-Z0-9]{2}\d{2}$/.test(t) || /^[A-Z]{4}\d{2}$/.test(t);

export default function Porton({ accesos, data }) {
  const dueno = {};
  data.unidades.forEach((u) => u.vehiculos.forEach((v) => { dueno[v.patente] = u.numero; }));
  const total = data.unidades.reduce((s, u) => s + u.vehiculos.length, 0);
  const sticker = data.unidades.reduce((s, u) => s + u.vehiculos.filter((v) => v.sticker).length, 0);
  return (
    <div className="porton-vista">
      <header className="vista-cab">
        <h2>Portón</h2>
        <p>{total} patentes registradas, {sticker} con sticker. El lector de patentes y el sticker abren el mismo portón; ambas lecturas quedan aquí.</p>
      </header>
      {accesos.length === 0 && <p className="vacio">Aún no hay lecturas. Cuando un auto pase frente al lector aparecerá aquí.</p>}
      <ol className="pasadas">
        {accesos.map((a) => (
          <li key={a.id} className={a.permitido ? "pasa" : "niega"}>
            <time>{hora(a.creado)}</time>
            {esPatente(a.token.toUpperCase()) ? <Placa valor={a.token} estado={a.permitido ? "" : "roja"} /> : <code className="credencial">{a.token}</code>}
            <span className="res">{a.permitido ? "Abrió" : "No abrió"}</span>
            <span className="det">{a.permitido ? (dueno[a.token.toUpperCase()] ? `Depto ${dueno[a.token.toUpperCase()]}` : a.motivo) : a.motivo} · {a.punto}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
