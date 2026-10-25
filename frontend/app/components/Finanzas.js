import { useEffect, useMemo, useState } from "react";
import { clp } from "../../lib/api";
import { mensajeError } from "../../lib/validar";

const SECCIONES = [["gastos", "Gastos comunes"], ["cartola", "Cartola bancaria"], ["circular", "Circular"], ["medidores", "Medidores"]];
const mesActual = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };
const FILA = () => ({ k: Math.random().toString(36).slice(2), concepto: "", monto: "", tipo: "ordinario", base: "coeficiente", servicio: "agua" });

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
// Mensaje claro para el resultado de un envío masivo (el backend dice si se encoló o por qué no).
const textoEnvio = (r) => r.encolado ? { ok: true, t: "Se están enviando en segundo plano. Los que no tengan correo se omiten." }
  : { ok: false, t: r.motivo || "No se envió." };

function GenerarGastos({ api, unidades, onGenerado }) {
  const [periodo, setPeriodo] = useState(mesActual());
  const [venc, setVenc] = useState("");
  const [filas, setFilas] = useState([FILA()]);
  const [err, setErr] = useState({});
  const [confirmar, setConfirmar] = useState(false);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const total = filas.reduce((s, f) => s + (Number(f.monto) || 0), 0);
  const setFila = (k, campo, v) => setFilas(filas.map((f) => (f.k === k ? { ...f, [campo]: v } : f)));

  const validar = () => {
    const x = {};
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(periodo)) x.periodo = "Elige el mes y el año.";
    if (!venc) x.venc = "Indica la fecha de vencimiento.";
    filas.forEach((f) => {
      if (!f.concepto.trim()) x[`c${f.k}`] = "Escribe el concepto.";
      if (!(Number(f.monto) > 0)) x[`m${f.k}`] = "El monto debe ser mayor que 0.";
    });
    setErr(x);
    return Object.keys(x).length === 0;
  };
  const pedirConfirmacion = (e) => { e.preventDefault(); setMsg(null); if (validar()) setConfirmar(true); else setMsg({ ok: false, t: "Revisa los campos marcados." }); };
  const generar = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.generarGastos({ periodo, vencimiento: venc, gastos: filas.map(({ k, ...g }) => ({ ...g, concepto: g.concepto.trim(), monto: Number(g.monto) })) });
      setMsg({ ok: true, t: `Gastos de ${periodo} generados: ${clp(r.total)} repartidos entre ${r.unidades} departamentos.` });
      setConfirmar(false); setFilas([FILA()]); onGenerado();
    } catch (e) { setMsg({ ok: false, t: mensajeError(e.detail ?? e.message) }); setConfirmar(false); }
    setBusy(false);
  };

  return (
    <form className="form-admin" onSubmit={pedirConfirmacion} noValidate aria-labelledby="gg-titulo">
      <h3 id="gg-titulo">Generar gastos comunes</h3>
      <div className="grid-form">
        <Campo id="gg-periodo" label="Mes" error={err.periodo}><input id="gg-periodo" type="month" value={periodo} onChange={(e) => setPeriodo(e.target.value)} aria-invalid={!!err.periodo} /></Campo>
        <Campo id="gg-venc" label="Vence el" error={err.venc}><input id="gg-venc" type="date" value={venc} onChange={(e) => setVenc(e.target.value)} aria-invalid={!!err.venc} /></Campo>
      </div>
      <fieldset className="gastos-filas">
        <legend>Gastos del mes</legend>
        {filas.map((f, i) => (
          <div className="gasto-fila" key={f.k}>
            <Campo id={`gg-c-${f.k}`} label={i === 0 ? "Concepto" : `Concepto ${i + 1}`} error={err[`c${f.k}`]}>
              <input id={`gg-c-${f.k}`} value={f.concepto} onChange={(e) => setFila(f.k, "concepto", e.target.value)} maxLength={80} placeholder="Administración, agua, remuneraciones…" aria-invalid={!!err[`c${f.k}`]} />
            </Campo>
            <Campo id={`gg-m-${f.k}`} label="Monto total (CLP)" error={err[`m${f.k}`]}>
              <input id={`gg-m-${f.k}`} type="number" min="1" step="1" value={f.monto} onChange={(e) => setFila(f.k, "monto", e.target.value)} aria-invalid={!!err[`m${f.k}`]} />
            </Campo>
            <Campo id={`gg-t-${f.k}`} label="Tipo">
              <select id={`gg-t-${f.k}`} value={f.tipo} onChange={(e) => setFila(f.k, "tipo", e.target.value)}><option value="ordinario">Ordinario</option><option value="extraordinario">Extraordinario</option></select>
            </Campo>
            <Campo id={`gg-b-${f.k}`} label="Se reparte por">
              <select id={`gg-b-${f.k}`} value={f.base} onChange={(e) => setFila(f.k, "base", e.target.value)}><option value="coeficiente">Coeficiente de copropiedad</option><option value="consumo">Consumo del medidor</option></select>
            </Campo>
            {f.base === "consumo" && (
              <Campo id={`gg-s-${f.k}`} label="Servicio medido">
                <select id={`gg-s-${f.k}`} value={f.servicio} onChange={(e) => setFila(f.k, "servicio", e.target.value)}><option value="agua">Agua</option><option value="gas">Gas</option><option value="calefaccion">Calefacción</option></select>
              </Campo>)}
            {filas.length > 1 && <button type="button" className="mini" onClick={() => setFilas(filas.filter((x) => x.k !== f.k))} aria-label={`Quitar gasto ${i + 1}`}>Quitar</button>}
          </div>))}
        <button type="button" className="btn sec" onClick={() => setFilas([...filas, FILA()])}>Agregar otro gasto</button>
      </fieldset>
      <p className="total-gastos">Total del mes: <b>{clp(total)}</b> entre {unidades} departamentos</p>
      {!confirmar && <div className="acciones"><button className="btn">Revisar y generar</button></div>}
      {confirmar && (
        <div className="aviso err" role="alertdialog" aria-label="Confirmar generación de gastos comunes">
          <p>Se emitirán <b>{clp(total)}</b> a {unidades} departamentos por {periodo}. Un mes ya generado no se puede volver a generar. ¿Continuar?</p>
          <button type="button" className="btn" disabled={busy} onClick={generar}>Sí, generar</button>{" "}
          <button type="button" className="btn sec" onClick={() => setConfirmar(false)}>Volver</button>
        </div>)}
      <Aviso msg={msg} />
    </form>
  );
}

function Periodos({ periodos, api }) {
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(null);
  const enviar = async (p) => {
    setBusy(p); setMsg(null);
    try { setMsg(textoEnvio(await api.enviarGastos(p))); } catch (e) { setMsg({ ok: false, t: mensajeError(e.detail ?? e.message) }); }
    setBusy(null);
  };
  return (
    <section aria-labelledby="pg-titulo" className="lista-reservas">
      <h3 id="pg-titulo">Meses generados</h3>
      {periodos.length === 0 ? <p className="vacio">Aún no se genera ningún mes.</p> : (
        <table className="tabla">
          <thead><tr><th>Mes</th><th className="der">Emitido</th><th className="der">Por cobrar</th><th>Deptos</th><th><span className="solo-lector">Acciones</span></th></tr></thead>
          <tbody>{periodos.map((p) => (
            <tr key={p.periodo}><td className="n">{p.periodo}</td><td className="der">{clp(p.emitido)}</td><td className="der">{clp(p.pendiente)}</td><td>{p.unidades}</td>
              <td><button className="mini" disabled={busy === p.periodo} onClick={() => enviar(p.periodo)} aria-label={`Enviar el gasto común de ${p.periodo} por correo`}>Enviar por correo</button></td></tr>))}</tbody>
        </table>)}
      <Aviso msg={msg} />
    </section>
  );
}

function Cartola({ api, onListo }) {
  const [archivo, setArchivo] = useState(null);
  const [res, setRes] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const enviar = async (e) => {
    e.preventDefault(); setMsg(null); setRes(null);
    if (!archivo) { setMsg({ ok: false, t: "Elige el archivo CSV de la cartola." }); return; }
    if (archivo.size > 5_000_000) { setMsg({ ok: false, t: "El archivo supera 5 MB. Divídalo por meses." }); return; }
    setBusy(true);
    try { setRes(await api.conciliar(archivo)); onListo(); } catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
    setBusy(false);
  };
  return (
    <form className="form-admin" onSubmit={enviar} noValidate aria-labelledby="ca-titulo">
      <h3 id="ca-titulo">Conciliar cartola bancaria</h3>
      <p className="ayuda">Archivo CSV con las columnas <code>fecha</code>, <code>descripcion</code>, <code>monto</code> y, si el banco lo da, <code>id</code>. Se buscan el RUT o el código de pago (CC-…) en la descripción y se abona a la deuda más antigua. Subir dos veces la misma cartola no duplica abonos.</p>
      <div className="campo">
        <label htmlFor="ca-archivo">Archivo de la cartola</label>
        <input id="ca-archivo" type="file" accept=".csv,text/csv" onChange={(e) => setArchivo(e.target.files?.[0] || null)} />
      </div>
      <div className="acciones"><button className="btn" disabled={busy}>Conciliar</button></div>
      <Aviso msg={msg} />
      {res && (
        <div className="resultado-cartola" role="status">
          <p><b>{res.conciliados.length}</b> pagos conciliados, <b>{res.sin_match.length}</b> sin identificar, <b>{res.duplicados}</b> ya registrados.</p>
          {res.sin_match.length > 0 && (<>
            <h4>Sin identificar (revise a mano)</h4>
            <table className="tabla"><thead><tr><th>Descripción</th><th className="der">Monto</th></tr></thead>
              <tbody>{res.sin_match.map((m) => <tr key={m.id}><td>{m.descripcion}</td><td className="der">{clp(m.monto)}</td></tr>)}</tbody></table>
          </>)}
        </div>)}
    </form>
  );
}

function Circular({ api }) {
  const [asunto, setAsunto] = useState("");
  const [cuerpo, setCuerpo] = useState("");
  const [err, setErr] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const enviar = async (e) => {
    e.preventDefault(); setMsg(null);
    const x = {};
    if (!asunto.trim()) x.asunto = "Escribe el asunto.";
    if (!cuerpo.trim()) x.cuerpo = "Escribe el mensaje.";
    setErr(x);
    if (Object.keys(x).length) return;
    setBusy(true);
    try {
      // Texto plano del administrador → párrafos HTML escapados (nunca HTML suelto en el correo).
      const html = cuerpo.trim().split(/\n{2,}/).map((p) => `<p>${esc(p).replace(/\n/g, "<br>")}</p>`).join("");
      setMsg(textoEnvio(await api.enviarCircular({ asunto: asunto.trim(), cuerpo_html: html })));
    } catch (x2) { setMsg({ ok: false, t: mensajeError(x2.detail ?? x2.message) }); }
    setBusy(false);
  };
  return (
    <form className="form-admin" onSubmit={enviar} noValidate aria-labelledby="ci-titulo">
      <h3 id="ci-titulo">Enviar una circular</h3>
      <p className="ayuda">Se envía por correo a todos los residentes activos que tengan correo registrado.</p>
      <Campo id="ci-asunto" label="Asunto" error={err.asunto}><input id="ci-asunto" value={asunto} onChange={(e) => setAsunto(e.target.value)} maxLength={150} aria-invalid={!!err.asunto} /></Campo>
      <Campo id="ci-cuerpo" label="Mensaje" error={err.cuerpo} ayuda="Una línea en blanco separa los párrafos.">
        <textarea id="ci-cuerpo" rows={8} value={cuerpo} onChange={(e) => setCuerpo(e.target.value)} aria-invalid={!!err.cuerpo} />
      </Campo>
      <div className="acciones"><button className="btn" disabled={busy}>Enviar a los residentes</button></div>
      <Aviso msg={msg} />
    </form>
  );
}

function Medidores({ api, unidades }) {
  const orden = useMemo(() => [...unidades].sort((a, b) => a.numero.localeCompare(b.numero)), [unidades]);
  const [f, setF] = useState({ unidad_id: "", periodo: mesActual(), servicio: "agua", consumo: "" });
  const [err, setErr] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const enviar = async (e) => {
    e.preventDefault(); setMsg(null);
    const x = {};
    if (!f.unidad_id) x.unidad_id = "Elige el departamento.";
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(f.periodo)) x.periodo = "Elige el mes.";
    if (f.consumo === "" || Number(f.consumo) < 0) x.consumo = "Escribe el consumo (0 o más).";
    setErr(x);
    if (Object.keys(x).length) return;
    setBusy(true);
    try {
      await api.cargarLectura({ unidad_id: Number(f.unidad_id), periodo: f.periodo, servicio: f.servicio, consumo: Number(f.consumo) });
      setMsg({ ok: true, t: "Lectura guardada." }); setF({ ...f, consumo: "" });
    } catch (x2) { setMsg({ ok: false, t: mensajeError(x2.detail ?? x2.message) }); }
    setBusy(false);
  };
  return (
    <form className="form-admin" onSubmit={enviar} noValidate aria-labelledby="me-titulo">
      <h3 id="me-titulo">Lectura de medidor</h3>
      <p className="ayuda">Las lecturas del mes se usan al generar los gastos que se reparten por consumo.</p>
      <div className="grid-form">
        <Campo id="me-depto" label="Departamento" error={err.unidad_id}>
          <select id="me-depto" value={f.unidad_id} onChange={(e) => setF({ ...f, unidad_id: e.target.value })} aria-invalid={!!err.unidad_id}><option value="">Elegir…</option>{orden.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}</select>
        </Campo>
        <Campo id="me-periodo" label="Mes" error={err.periodo}><input id="me-periodo" type="month" value={f.periodo} onChange={(e) => setF({ ...f, periodo: e.target.value })} aria-invalid={!!err.periodo} /></Campo>
        <Campo id="me-serv" label="Servicio"><select id="me-serv" value={f.servicio} onChange={(e) => setF({ ...f, servicio: e.target.value })}><option value="agua">Agua</option><option value="gas">Gas</option><option value="calefaccion">Calefacción</option></select></Campo>
        <Campo id="me-cons" label="Consumo" error={err.consumo}><input id="me-cons" type="number" min="0" step="0.001" value={f.consumo} onChange={(e) => setF({ ...f, consumo: e.target.value })} aria-invalid={!!err.consumo} /></Campo>
      </div>
      <div className="acciones"><button className="btn" disabled={busy}>Guardar lectura</button></div>
      <Aviso msg={msg} />
    </form>
  );
}

export default function Finanzas({ api, data, onChange }) {
  const [sec, setSec] = useState("gastos");
  const [periodos, setPeriodos] = useState([]);
  const [errCarga, setErrCarga] = useState("");
  const cargar = async () => { try { setPeriodos(await api.periodosGastos()); setErrCarga(""); } catch (e) { setErrCarga(mensajeError(e.detail ?? e.message)); } };
  useEffect(() => { cargar(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <div className="finanzas-vista">
      <header className="vista-cab">
        <h2>Finanzas</h2>
        <p>Genere los gastos comunes del mes, concilie pagos con la cartola y avise a los residentes.</p>
      </header>
      <div className="subtabs" role="tablist" aria-label="Secciones de finanzas">
        {SECCIONES.map(([k, t]) => <button key={k} role="tab" aria-selected={sec === k} className={sec === k ? "tab on" : "tab"} onClick={() => setSec(k)}>{t}</button>)}
      </div>
      {errCarga && <p role="alert" className="aviso err">{errCarga}</p>}
      {sec === "gastos" && (<><GenerarGastos api={api} unidades={data.unidades.length} onGenerado={() => { cargar(); onChange(); }} /><Periodos periodos={periodos} api={api} /></>)}
      {sec === "cartola" && <Cartola api={api} onListo={onChange} />}
      {sec === "circular" && <Circular api={api} />}
      {sec === "medidores" && <Medidores api={api} unidades={data.unidades} />}
    </div>
  );
}
