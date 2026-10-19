import Placa from "./Placa";

const hora = (iso) => new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const esPatente = (t) => /^[A-Z]{2}[A-Z0-9]{2}\d{2}$/.test(t) || /^[A-Z]{4}\d{2}$/.test(t);
const FUENTE = { sticker: "Sticker", patente: "Patente", qr: "Código QR", tag: "Llavero" };

// Qué pasó con esta lectura, en palabras para el guardia o el técnico.
export function explicar(a) {
  if (a.permitido) return a.motivo;
  if (a.motivo.startsWith("Esperando")) return `${a.motivo}. Pase de nuevo para completar la lectura.`;
  if (a.motivo.startsWith("Lectura duplicada")) return "Repetición de la misma lectura: no se volvió a abrir.";
  return a.motivo;
}

export default function Porton({ accesos, data }) {
  const dueno = {};
  data.unidades.forEach((u) => u.vehiculos.forEach((v) => { dueno[v.patente] = u.numero; }));
  const total = data.unidades.reduce((s, u) => s + u.vehiculos.length, 0);
  const sticker = data.unidades.reduce((s, u) => s + u.vehiculos.filter((v) => v.sticker).length, 0);
  return (
    <div className="porton-vista">
      <header className="vista-cab">
        <h2>Portón</h2>
        <p>{total} patentes registradas, {sticker} con sticker. Cada lectura muestra si vino del sticker, de la patente o de un código QR, y por qué abrió o no.</p>
      </header>
      {accesos.length === 0 && <p className="vacio">Aún no hay lecturas. Cuando un auto pase frente al lector aparecerá aquí.</p>}
      <ol className="pasadas">
        {accesos.map((a) => (
          <li key={a.id} className={a.permitido ? "pasa" : "niega"}>
            <time>{hora(a.creado)}</time>
            {esPatente(a.token.toUpperCase()) ? <Placa valor={a.token} estado={a.permitido ? "" : "roja"} /> : <code className="credencial">{a.token.length > 8 ? "…" + a.token.slice(-8) : a.token}</code>}
            <span className="res">{a.permitido ? "Abrió" : "No abrió"}</span>
            <span className="det">
              {a.fuente && <span className={`fuente ${a.fuente}`}>{FUENTE[a.fuente] || a.fuente}</span>}
              {a.permitido && dueno[a.token.toUpperCase()] ? `Depto ${dueno[a.token.toUpperCase()]}` : explicar(a)}
              {" · "}{a.punto}
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}
