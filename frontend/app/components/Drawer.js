import { useState } from "react";
import Placa from "./Placa";
import { clp } from "../../lib/api";

export default function Drawer({ u, api, onClose, onChange }) {
  const [pat, setPat] = useState("");
  const [desc, setDesc] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const cupo = u.estacionamientos - u.vehiculos.length;

  const run = async (fn, ok) => {
    setBusy(true); setMsg(null);
    try { await fn(); setMsg({ ok: true, t: ok }); await onChange(); }
    catch (e) { setMsg({ ok: false, t: e.message }); }
    setBusy(false);
  };
  return (
    <aside className="drawer" aria-label={`Departamento ${u.numero}`}>
      <button className="cerrar" onClick={onClose} aria-label="Cerrar">×</button>
      <h2 className="drawer-num">{u.numero}</h2>
      <p className="drawer-sub">Código de pago <code>{u.codigo_cobro}</code></p>

      <section>
        <h3>Cuenta</h3>
        {u.deuda > 0 ? (
          <>
            <p className="monto mal">{clp(u.deuda)}</p>
            <p className="nota">{u.vencida > 0 ? `${clp(u.vencida)} vencido.` : "Aún no vence."}</p>
            <button disabled={busy} className="btn" onClick={() => run(() => api.recordatorios({ unidad_ids: [u.id], canales: ["whatsapp", "email"] }), "Recordatorio enviado")}>
              Enviar recordatorio de pago
            </button>
          </>
        ) : <p className="monto bien">Al día</p>}
      </section>

      <section>
        <h3>Residentes</h3>
        {u.residentes.length === 0 && <p className="nota">Sin residentes registrados. Se cargan desde la base de datos.</p>}
        <ul className="lista">
          {u.residentes.map((r) => (
            <li key={r.id}><b>{r.nombre}</b><span>{r.telefono ? "+" + r.telefono : "sin teléfono"}<br />{r.email || "sin correo"}</span></li>
          ))}
        </ul>
      </section>

      <section>
        <h3>Vehículos y patentes <small>{u.vehiculos.length} de {u.estacionamientos}</small></h3>
        {u.estacionamientos === 0 && <p className="nota">Este departamento no tiene estacionamiento asignado.</p>}
        <ul className="lista autos-l">
          {u.vehiculos.map((v) => (
            <li key={v.id}>
              <Placa valor={v.patente} />
              <span>{v.descripcion || "Sin descripción"}{v.sticker ? " · con sticker" : " · sólo patente"}</span>
              <button className="mini" disabled={busy} onClick={() => run(() => api.delVehiculo(v.id), "Vehículo dado de baja")}>Dar de baja</button>
            </li>
          ))}
        </ul>
        {cupo > 0 && (
          <form className="form" onSubmit={(e) => { e.preventDefault(); run(async () => { await api.addVehiculo({ unidad_id: u.id, patente: pat, descripcion: desc }); setPat(""); setDesc(""); }, "Vehículo registrado"); }}>
            <label>Patente<input value={pat} onChange={(e) => setPat(e.target.value.toUpperCase())} placeholder="BBCD12" maxLength={8} required autoComplete="off" /></label>
            <label>Vehículo<input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Mazda 3 gris" maxLength={80} /></label>
            <button className="btn" disabled={busy}>Registrar vehículo</button>
          </form>
        )}
      </section>
      {msg && <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>}
    </aside>
  );
}
