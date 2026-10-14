// Patente chilena: fondo blanco, caracteres en relieve, franja de país.
export default function Placa({ valor, estado, pequena }) {
  const v = (valor || "").toUpperCase();
  const fmt = v.length === 6 ? `${v.slice(0, 2)}·${v.slice(2, 4)}·${v.slice(4)}` : v;
  return (
    <span className={`placa ${estado || ""} ${pequena ? "placa-s" : ""}`} aria-label={`Patente ${v}`}>
      <i className="placa-pais" aria-hidden="true">CHILE</i>
      <b>{fmt || "—"}</b>
    </span>
  );
}
