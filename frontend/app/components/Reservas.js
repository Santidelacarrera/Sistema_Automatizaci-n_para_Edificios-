import { useEffect, useMemo, useState } from "react";
import { mensajeError } from "../../lib/validar";

const pad = (n) => String(n).padStart(2, "0");
// Valor para <input type="datetime-local"> en hora local del navegador.
const local = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const proximaHora = (masHoras = 1) => { const d = new Date(); d.setMinutes(0, 0, 0); d.setHours(d.getHours() + masHoras); return d; };
const fmt = (iso) => new Date(iso).toLocaleString("es-CL", { dateStyle: "short", timeStyle: "short" });

function Aviso({ msg }) {
  return msg ? <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p> : null;
}
function Campo({ id, label, error, ayuda, children }) {
  return (
    <div className="campo">
      <label htmlFor={id}>{label}</label>
      {children}
      {ayuda && !error && <span className="ayuda">{ayuda}</span>}
      {error && <span className="error-campo">{error}</span>}
    </div>
  );
}

function ReservarVisita({ api, data, onChange }) {
  const unidades = useMemo(() => [...data.unidades].sort((a, b) => a.numero.localeCompare(b.numero)), [data]);
  const [f, setF] = useState({ unidad_id: "", nombre_visita: "", patente: "", usa_estacionamiento: true, desde: local(proximaHora(1)), hasta: local(proximaHora(3)) });
  const [err, setErr] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [qr, setQr] = useState(null); // { url, nombre, depto }
  useEffect(() => () => { if (qr?.url?.startsWith("blob:")) URL.revokeObjectURL(qr.url); }, [qr]);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const enviar = async (e) => {
    e.preventDefault();
    const x = {};
    if (!f.unidad_id) x.unidad_id = "Elige el departamento que recibe la visita.";
    if (!f.nombre_visita.trim()) x.nombre_visita = "Escribe el nombre de la visita.";
    if (f.patente && !/^[A-Za-z0-9\- ]{5,8}$/.test(f.patente)) x.patente = "La patente tiene entre 5 y 7 letras o números.";
    if (!f.desde || !f.hasta || new Date(f.hasta) <= new Date(f.desde)) x.hasta = "La salida debe ser posterior a la llegada.";
    setErr(x);
    if (Object.keys(x).length) { setMsg({ ok: false, t: "Revisa los campos marcados." }); return; }
    setBusy(true); setMsg(null); setQr(null);
    try {
      const r = await api.reservarVisita({ ...f, unidad_id: Number(f.unidad_id), nombre_visita: f.nombre_visita.trim() });
      const url = await api.qrVisita(r.id);
      setQr({ url, nombre: f.nombre_visita.trim(), depto: unidades.find((u) => u.id === Number(f.unidad_id))?.numero });
      setMsg({ ok: true, t: "Visita reservada. Muestre o envíe el QR a la visita." });
      setF({ ...f, nombre_visita: "", patente: "" });
      onChange();
    } catch (x2) { setMsg({ ok: false, t: mensajeError(x2.detail ?? x2.message) }); }
    setBusy(false);
  };

  return (
    <form className="form-admin" onSubmit={enviar} noValidate aria-labelledby="rv-titulo">
      <h3 id="rv-titulo">Reservar una visita</h3>
      <div className="grid-form">
        <Campo id="rv-depto" label="Departamento" error={err.unidad_id}>
          <select id="rv-depto" value={f.unidad_id} onChange={set("unidad_id")} aria-invalid={!!err.unidad_id}>
            <option value="">Elegir…</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}
          </select>
        </Campo>
        <Campo id="rv-nombre" label="Nombre de la visita" error={err.nombre_visita}>
          <input id="rv-nombre" value={f.nombre_visita} onChange={set("nombre_visita")} maxLength={120} aria-invalid={!!err.nombre_visita} />
        </Campo>
        <Campo id="rv-llega" label="Llega"><input id="rv-llega" type="datetime-local" value={f.desde} onChange={set("desde")} /></Campo>
        <Campo id="rv-sale" label="Se va" error={err.hasta}><input id="rv-sale" type="datetime-local" value={f.hasta} onChange={set("hasta")} aria-invalid={!!err.hasta} /></Campo>
        <Campo id="rv-pat" label="Patente (opcional)" error={err.patente} ayuda="Con patente, el lector de la cámara abre sin mostrar el QR.">
          <input id="rv-pat" value={f.patente} onChange={(e) => setF({ ...f, patente: e.target.value.toUpperCase() })} maxLength={8} aria-invalid={!!err.patente} autoComplete="off" />
        </Campo>
        <label className="chk"><input type="checkbox" checked={f.usa_estacionamiento} onChange={set("usa_estacionamiento")} />Usa estacionamiento de visitas</label>
      </div>
      <div className="acciones"><button className="btn" disabled={busy}>Reservar visita</button></div>
      <Aviso msg={msg} />
      {qr && (
        <figure className="qr-visita">
          <img src={qr.url} alt={`Código QR de la visita de ${qr.nombre} al departamento ${qr.depto}`} width={160} height={160} />
          <figcaption>{qr.nombre}, depto {qr.depto}. El QR sirve sólo dentro del horario reservado.</figcaption>
        </figure>
      )}
    </form>
  );
}

function ReservarEspacio({ api, data, espacios, onGuardado }) {
  const unidades = useMemo(() => [...data.unidades].sort((a, b) => a.numero.localeCompare(b.numero)), [data]);
  const [f, setF] = useState({ espacio_id: "", unidad_id: "", desde: local(proximaHora(24)), hasta: local(proximaHora(28)) });
  const [err, setErr] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const enviar = async (e) => {
    e.preventDefault();
    const x = {};
    if (!f.espacio_id) x.espacio_id = "Elige el espacio.";
    if (!f.unidad_id) x.unidad_id = "Elige el departamento.";
    if (new Date(f.hasta) <= new Date(f.desde)) x.hasta = "El término debe ser posterior al inicio.";
    setErr(x);
    if (Object.keys(x).length) { setMsg({ ok: false, t: "Revisa los campos marcados." }); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await api.reservarEspacio({ espacio_id: Number(f.espacio_id), unidad_id: Number(f.unidad_id), desde: f.desde, hasta: f.hasta });
      setMsg({ ok: true, t: r.tarifa > 0 ? `Reserva confirmada. Se cargó la tarifa de $${Number(r.tarifa).toLocaleString("es-CL")} a la cuenta del departamento.` : "Reserva confirmada." });
      onGuardado();
    } catch (x2) {
      const d = x2.detail;
      setMsg({ ok: false, t: d?.motivos ? d.motivos.join(" ") : mensajeError(d ?? x2.message) });
    }
    setBusy(false);
  };

  return (
    <form className="form-admin" onSubmit={enviar} noValidate aria-labelledby="re-titulo">
      <h3 id="re-titulo">Reservar un espacio común</h3>
      {espacios.length === 0 ? <p className="vacio">No hay espacios comunes configurados. Se cargan en la base de datos del edificio.</p> : (
        <>
          <div className="grid-form">
            <Campo id="re-esp" label="Espacio" error={err.espacio_id}>
              <select id="re-esp" value={f.espacio_id} onChange={set("espacio_id")} aria-invalid={!!err.espacio_id}>
                <option value="">Elegir…</option>{espacios.map((e) => <option key={e.id} value={e.id}>{e.nombre}{e.tarifa > 0 ? ` ($${Number(e.tarifa).toLocaleString("es-CL")})` : ""}</option>)}
              </select>
            </Campo>
            <Campo id="re-depto" label="Departamento" error={err.unidad_id}>
              <select id="re-depto" value={f.unidad_id} onChange={set("unidad_id")} aria-invalid={!!err.unidad_id}>
                <option value="">Elegir…</option>{unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}
              </select>
            </Campo>
            <Campo id="re-ini" label="Desde"><input id="re-ini" type="datetime-local" value={f.desde} onChange={set("desde")} /></Campo>
            <Campo id="re-fin" label="Hasta" error={err.hasta}><input id="re-fin" type="datetime-local" value={f.hasta} onChange={set("hasta")} aria-invalid={!!err.hasta} /></Campo>
          </div>
          <p className="ayuda">Se aplican las reglas del edificio: horario, máximo por mes, morosidad y anticipación.</p>
          <div className="acciones"><button className="btn" disabled={busy}>Reservar espacio</button></div>
        </>
      )}
      <Aviso msg={msg} />
    </form>
  );
}

function ListaReservas({ reservas, api, onCambio }) {
  const [confirmar, setConfirmar] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const cancelar = async (id) => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.cancelarReserva(id);
      setMsg({ ok: true, t: r.multa > 0 ? `Reserva cancelada. Se cargó una multa de $${Number(r.multa).toLocaleString("es-CL")} por cancelar con poco aviso.` : "Reserva cancelada sin multa." });
      setConfirmar(null); onCambio();
    } catch (e) { setMsg({ ok: false, t: mensajeError(e.detail ?? e.message) }); }
    setBusy(false);
  };
  return (
    <section aria-labelledby="lr-titulo" className="lista-reservas">
      <h3 id="lr-titulo">Reservas de espacios</h3>
      {reservas.length === 0 ? <p className="vacio">No hay reservas de espacios comunes.</p> : (
        <table className="tabla">
          <thead><tr><th>Espacio</th><th>Depto</th><th>Desde</th><th>Hasta</th><th>Estado</th><th><span className="solo-lector">Acciones</span></th></tr></thead>
          <tbody>{reservas.map((r) => (
            <tr key={r.id} className={r.estado === "cancelada" ? "atenuada" : ""}>
              <td>{r.espacio}</td><td className="n">{r.unidad}</td><td>{fmt(r.desde)}</td><td>{fmt(r.hasta)}</td>
              <td>{r.estado === "confirmada" ? "Confirmada" : "Cancelada"}</td>
              <td>{r.estado === "confirmada" && new Date(r.hasta) > new Date() && (
                confirmar === r.id
                  ? <span className="confirma">¿Cancelar? <button className="mini" disabled={busy} onClick={() => cancelar(r.id)}>Sí, cancelar</button> <button className="mini neutro" onClick={() => setConfirmar(null)}>No</button></span>
                  : <button className="mini" onClick={() => setConfirmar(r.id)} aria-label={`Cancelar reserva de ${r.espacio} del departamento ${r.unidad}`}>Cancelar</button>)}</td>
            </tr>))}</tbody>
        </table>
      )}
      <Aviso msg={msg} />
    </section>
  );
}

export default function Reservas({ api, data, onChange }) {
  const [espacios, setEspacios] = useState([]);
  const [reservas, setReservas] = useState([]);
  const [errCarga, setErrCarga] = useState("");
  const cargar = async () => {
    try { setReservas(await api.reservasEspacio()); setErrCarga(""); } catch (e) { setErrCarga(mensajeError(e.detail ?? e.message)); }
  };
  useEffect(() => { api.espacios().then(setEspacios).catch(() => setEspacios([])); cargar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="reservas-vista">
      <header className="vista-cab">
        <h2>Reservas</h2>
        <p>Visitas con QR y espacios comunes. Cada reserva respeta los cupos y las reglas del edificio.</p>
      </header>
      {errCarga && <p role="alert" className="aviso err">{errCarga}</p>}
      <div className="dos-columnas">
        <ReservarVisita api={api} data={data} onChange={onChange} />
        <ReservarEspacio api={api} data={data} espacios={espacios} onGuardado={cargar} />
      </div>
      <ListaReservas reservas={reservas} api={api} onCambio={cargar} />
    </div>
  );
}
