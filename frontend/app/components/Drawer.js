import { useEffect, useState } from "react";
import Placa from "./Placa";
import { clp } from "../../lib/api";

const ETQ_ESTADO = { activo: "Activo", perdido: "Perdido", bloqueado: "Bloqueado" };
const COMO_FECHA = (iso) => (iso ? new Date(iso).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" }) : "Nunca");
const ULTIMOS = (uid) => uid.slice(-8);

export default function Drawer({ u, api, onClose, onChange, esAdmin, unidades = [] }) {
  const [pat, setPat] = useState("");
  const [desc, setDesc] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [stickers, setStickers] = useState(null);     // null = cargando o sin permiso
  const [destino, setDestino] = useState({});         // uid -> unidad elegida para reasignar
  const [vincular, setVincular] = useState({});       // vehiculo id -> sticker elegido
  const cupo = u.estacionamientos - u.vehiculos.length;

  const cargarStickers = async () => {
    if (!esAdmin) return;
    try { setStickers((await api.tags()).filter((t) => t.unidad_id === u.id)); }
    catch (e) { setMsg({ ok: false, t: e.message }); }
  };
  useEffect(() => { cargarStickers(); }, [u.id, esAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (fn, ok) => {
    setBusy(true); setMsg(null);
    try { await fn(); setMsg({ ok: true, t: ok }); await onChange(); await cargarStickers(); }
    catch (e) { setMsg({ ok: false, t: e.message }); }
    setBusy(false);
  };
  const libres = (stickers || []).filter((t) => !t.patente && t.estado === "activo");
  const tagDeVehiculo = (patente) => (stickers || []).find((t) => t.patente === patente);

  return (
    <aside className="drawer" aria-label={`Departamento ${u.numero}`}>
      <button className="cerrar" onClick={onClose} aria-label="Cerrar ficha del departamento">×</button>
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
          {u.vehiculos.map((v) => {
            const tag = tagDeVehiculo(v.patente);
            return (
              <li key={v.id}>
                <Placa valor={v.patente} />
                <span>
                  {v.descripcion || "Sin descripción"}
                  {" · "}{tag ? `sticker ${ETQ_ESTADO[tag.estado]?.toLowerCase() || tag.estado}` : v.sticker ? "con sticker" : "sólo patente"}
                </span>
                <div className="acciones-fila">
                  {esAdmin && tag && (
                    <button className="mini" disabled={busy} onClick={() => run(() => api.desvincularTag(tag.id), "Sticker quitado del vehículo")}>
                      Quitar sticker
                    </button>
                  )}
                  <button className="mini" disabled={busy} onClick={() => run(() => api.delVehiculo(v.id), "Vehículo dado de baja")}>Dar de baja</button>
                </div>
                {esAdmin && !tag && libres.length > 0 && (
                  <form className="form-fila" onSubmit={(e) => { e.preventDefault(); const t = libres.find((x) => String(x.id) === vincular[v.id]); if (!t) return; run(() => api.vincularTag(t.id, v.id), `Sticker asociado a ${v.patente}`); }}>
                    <label>Asociar sticker
                      <select value={vincular[v.id] || ""} onChange={(e) => setVincular({ ...vincular, [v.id]: e.target.value })}>
                        <option value="">Elige un sticker…</option>
                        {libres.map((t) => <option key={t.id} value={t.id}>…{ULTIMOS(t.uid)}</option>)}
                      </select>
                    </label>
                    <button className="mini" disabled={busy || !vincular[v.id]}>Asociar</button>
                  </form>
                )}
              </li>
            );
          })}
        </ul>
        {cupo > 0 && (
          <form className="form" onSubmit={(e) => { e.preventDefault(); run(async () => { await api.addVehiculo({ unidad_id: u.id, patente: pat, descripcion: desc }); setPat(""); setDesc(""); }, "Vehículo registrado"); }}>
            <label>Patente<input value={pat} onChange={(e) => setPat(e.target.value.toUpperCase())} placeholder="BBCD12" maxLength={8} required autoComplete="off" /></label>
            <label>Vehículo<input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Mazda 3 gris" maxLength={80} /></label>
            <button className="btn" disabled={busy}>Registrar vehículo</button>
          </form>
        )}
      </section>

      {esAdmin && (
        <section aria-labelledby="stickers-u">
          <h3 id="stickers-u">Stickers UHF <small>{stickers ? stickers.length : "…"}</small></h3>
          {stickers && stickers.length === 0 && <p className="nota">Este departamento no tiene stickers. Se registran en Administración → Tags RFID o con la importación CSV.</p>}
          <ul className="lista stickers-l">
            {(stickers || []).map((t) => (
              <li key={t.id} className={`sticker-${t.estado}`}>
                <div className="sticker-cab">
                  <code title={t.uid}>…{ULTIMOS(t.uid)}</code>
                  <span className={`chip-estado ${t.estado}`}>{ETQ_ESTADO[t.estado] || t.estado}</span>
                </div>
                <span>{t.formato === "wiegand" ? "Wiegand" : "EPC"} · patente {t.patente || "sin asociar"} · última lectura {COMO_FECHA(t.ultima_lectura)}</span>
                <div className="acciones-fila">
                  {t.estado !== "activo" && <button className="mini" disabled={busy} aria-label={`Activar sticker ${ULTIMOS(t.uid)}`} onClick={() => run(() => api.activarTag(t.id), "Sticker activado")}>Activar</button>}
                  {t.estado === "activo" && <button className="mini" disabled={busy} aria-label={`Marcar perdido el sticker ${ULTIMOS(t.uid)}`} onClick={() => run(() => api.perderTag(t.id, "reportado perdido desde el panel"), "Sticker marcado como perdido: ya no abre")}>Marcar perdido</button>}
                  {t.estado !== "bloqueado" && <button className="mini" disabled={busy} aria-label={`Bloquear sticker ${ULTIMOS(t.uid)}`} onClick={() => run(() => api.bloquearTag(t.id, "bloqueado desde el panel"), "Sticker bloqueado")}>Bloquear</button>}
                </div>
                {unidades.length > 1 && (
                  <form className="form-fila" onSubmit={(e) => { e.preventDefault(); if (!destino[t.uid]) return; run(() => api.reasignarTag(t.id, { unidad_id: Number(destino[t.uid]) }), "Sticker reasignado: el vehículo anterior quedó sin sticker"); }}>
                    <label>Reasignar a
                      <select value={destino[t.uid] || ""} onChange={(e) => setDestino({ ...destino, [t.uid]: e.target.value })}>
                        <option value="">Elige un departamento…</option>
                        {unidades.filter((x) => x.id !== u.id).map((x) => <option key={x.id} value={x.id}>{x.numero}</option>)}
                      </select>
                    </label>
                    <button className="mini" disabled={busy || !destino[t.uid]}>Reasignar</button>
                  </form>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
      {msg && <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>}
    </aside>
  );
}
