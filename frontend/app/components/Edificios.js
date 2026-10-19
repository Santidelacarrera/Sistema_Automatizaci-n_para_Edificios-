import { clp } from "../../lib/api";

// Vista del superadmin: un renglón por edificio con su estado de cobranza. "Abrir" cambia el edificio activo.
export default function Edificios({ lista, activo, onAbrir, error }) {
  return (
    <div className="edificios-vista">
      <header className="vista-cab">
        <h2>Edificios</h2>
        <p>Cada edificio tiene sus propios residentes, accesos y cobranza. Abra uno para trabajar en él.</p>
      </header>
      {error && <p role="alert" className="aviso err">{error}</p>}
      {!error && lista.length === 0 && <p className="vacio">Cargando edificios…</p>}
      {lista.length > 0 && (
        <table className="tabla">
          <thead><tr><th>Edificio</th><th className="der">Departamentos</th><th className="der">Residentes</th><th className="der">Deuda total</th><th><span className="sr">Acción</span></th></tr></thead>
          <tbody>{lista.map((e) => (
            <tr key={e.id}>
              <td><b>{e.nombre}</b> <code>{e.id}</code></td>
              <td className="der">{e.unidades}</td><td className="der">{e.residentes}</td>
              <td className="der">{clp(e.deuda_total)}</td>
              <td><button className="mini" onClick={() => onAbrir(e.id)} aria-label={`Abrir ${e.nombre}`}>{e.id === activo ? "Abierto" : "Abrir"}</button></td>
            </tr>))}</tbody>
        </table>
      )}
    </div>
  );
}
