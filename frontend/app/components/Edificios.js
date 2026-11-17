import { clp } from "../../lib/api";
import { useState } from "react";

// Vista del superadmin: un renglón por edificio con su estado de cobranza. "Abrir" cambia el edificio activo.
export default function Edificios({ lista, activo, onAbrir, error, onCrear, onEditar }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmar, setConfirmar] = useState(null);
  const crear = async (e) => {
    e.preventDefault(); const form = e.currentTarget; const data = Object.fromEntries(new FormData(form));
    setBusy(true); setMsg("");
    try { await onCrear({ ...data, cupos_visitas: Number(data.cupos_visitas) }); form.reset(); setMsg("Edificio creado. Ábralo para registrar unidades y residentes."); }
    catch (e) { setMsg(e.message); } finally { setBusy(false); }
  };
  return (
    <div className="edificios-vista">
      <header className="vista-cab">
        <h2>Edificios</h2>
        <p>Cada edificio tiene sus propios residentes, accesos y cobranza. Abra uno para trabajar en él.</p>
      </header>
      {error && <p role="alert" className="aviso err">{error}</p>}
      {onCrear && <form className="fila-form" onSubmit={crear}>
        <label>Identificador<input name="id" pattern="[a-z0-9][a-z0-9_-]{1,39}" required /></label>
        <label>Nombre del edificio<input name="nombre" minLength={2} maxLength={120} required /></label>
        <label>Cupos de visitas<input name="cupos_visitas" type="number" min="0" max="10000" defaultValue="6" required /></label>
        <button className="btn" disabled={busy}>Crear edificio</button>
      </form>}
      {msg && <p role="status">{msg}</p>}
      {confirmar && <div className="confirmar"><p>Suspender {confirmar.nombre} impedirá el acceso a sus usuarios y lectores.</p>
        <button className="btn peligro" disabled={busy} onClick={async () => { setBusy(true); try { await onEditar(confirmar.id, { activo: false }); setConfirmar(null); } catch (e) { setMsg(e.message); } finally { setBusy(false); } }}>Confirmar suspensión</button>
        <button className="btn sec" onClick={() => setConfirmar(null)}>Cancelar</button></div>}
      {!error && lista.length === 0 && <p className="vacio">Cargando edificios…</p>}
      {lista.length > 0 && (
        <table className="tabla">
          <thead><tr><th>Edificio</th><th className="der">Departamentos</th><th className="der">Residentes</th><th className="der">Deuda total</th><th><span className="sr">Acción</span></th></tr></thead>
          <tbody>{lista.map((e) => (
            <tr key={e.id}>
              <td><b>{e.nombre}</b> <code>{e.id}</code></td>
              <td className="der">{e.unidades}</td><td className="der">{e.residentes}</td>
              <td className="der">{clp(e.deuda_total)}</td>
              <td><button className="mini" onClick={() => onAbrir(e.id)} aria-label={`Abrir ${e.nombre}`}>{e.id === activo ? "Abierto" : "Abrir"}</button>
                {onEditar && <button className="mini" disabled={busy} onClick={async () => {
                  if (e.activo) { setConfirmar(e); return; }
                  setBusy(true); try { await onEditar(e.id, { activo: true }); } catch (x) { setMsg(x.message); } finally { setBusy(false); }
                }}>{e.activo ? "Suspender" : "Activar"}</button>}</td>
            </tr>))}</tbody>
        </table>
      )}
    </div>
  );
}
