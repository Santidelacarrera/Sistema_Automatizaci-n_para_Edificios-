"use client";
import { useCallback, useEffect, useState } from "react";
import { clp } from "../../lib/api";

const fh = (iso) => (iso ? new Date(iso).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");
const CAT = { aviso: "Aviso", mantencion: "Mantención", asamblea: "Asamblea", urgente: "Urgente" };

function useLista(cargarFn, dep) {
  const [lista, setLista] = useState([]);
  const [err, setErr] = useState("");
  const recargar = useCallback(async () => {
    try { setLista(await cargarFn()); setErr(""); } catch (e) { setErr(e.message); }
  }, dep); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { recargar(); }, [recargar]);
  return [lista, recargar, err];
}

function Estado({ msg }) {
  return msg ? <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p> : null;
}

export function Encomiendas({ api, data }) {
  const [lista, recargar, err] = useLista(() => api.encomiendas(), [api.encomiendas]);
  const [f, setF] = useState({ unidad_id: "", transportista: "", descripcion: "" });
  const [msg, setMsg] = useState(null);
  const registrar = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.recibirEncomienda({ ...f, unidad_id: Number(f.unidad_id) }); setF({ unidad_id: "", transportista: "", descripcion: "" }); setMsg({ ok: true, t: "Encomienda registrada; el residente fue avisado." }); await recargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const entregar = async (id) => {
    const quien = window.prompt("Nombre de quien retira el paquete");
    if (!quien || quien.trim().length < 2) return;
    try { await api.entregarEncomienda(id, quien.trim()); setMsg({ ok: true, t: "Entrega registrada con fecha y hora." }); await recargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const pendientes = lista.filter((x) => x.estado === "pendiente");
  return (
    <section aria-labelledby="h-enc">
      <h3 id="h-enc">Encomiendas en conserjería ({pendientes.length} por retirar)</h3>
      <form className="envio" onSubmit={registrar}>
        <label>Departamento
          <select value={f.unidad_id} onChange={(e) => setF({ ...f, unidad_id: e.target.value })} required>
            <option value="">Elegir…</option>
            {data.unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}
          </select></label>
        <label>Transportista
          <input list="transportistas" value={f.transportista} onChange={(e) => setF({ ...f, transportista: e.target.value })} maxLength={60} placeholder="Chilexpress" />
          <datalist id="transportistas">{["Chilexpress", "Mercado Libre", "Correos de Chile", "Starken", "Blue Express"].map((t) => <option key={t} value={t} />)}</datalist></label>
        <label className="grande">Detalle (opcional)
          <input value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} maxLength={200} placeholder="Caja mediana" /></label>
        <button className="btn" disabled={!f.unidad_id}>Registrar</button>
      </form>
      <Estado msg={msg} />{err && <p role="alert" className="aviso err">{err}</p>}
      {lista.length === 0 ? <p className="vacio">No hay encomiendas registradas.</p> : (
        <table className="tabla">
          <thead><tr><th>Depto</th><th>Transportista</th><th>Llegó</th><th>Estado</th><th /></tr></thead>
          <tbody>{lista.map((e) => (
            <tr key={e.id} className={e.estado === "entregada" ? "inactivo" : ""}>
              <td className="n">{e.unidad}</td><td>{e.transportista || "—"}{e.descripcion ? ` · ${e.descripcion}` : ""}</td>
              <td>{fh(e.recibida_at)}</td>
              <td>{e.estado === "entregada" ? `Retiró ${e.retirada_por} (${fh(e.entregada_at)})` : "Por retirar"}</td>
              <td className="acc">{e.estado === "pendiente" && <button className="mini" onClick={() => entregar(e.id)}>Entregar</button>}</td>
            </tr>))}</tbody>
        </table>)}
    </section>
  );
}

export function Comunicados({ api }) {
  const [lista, recargar, err] = useLista(() => api.comunicados(), [api.comunicados]);
  const [f, setF] = useState({ titulo: "", cuerpo: "", categoria: "aviso", fijado: false });
  const [msg, setMsg] = useState(null);
  const publicar = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.publicarComunicado(f); setF({ titulo: "", cuerpo: "", categoria: "aviso", fijado: false }); setMsg({ ok: true, t: "Comunicado publicado en el muro." }); await recargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const retirar = async (id) => { try { await api.retirarComunicado(id); await recargar(); } catch (x) { setMsg({ ok: false, t: x.message }); } };
  return (
    <section aria-labelledby="h-com">
      <h3 id="h-com">Muro de comunicados</h3>
      <form className="envio" onSubmit={publicar}>
        <label className="grande">Título<input value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} minLength={3} maxLength={160} required /></label>
        <label className="grande">Mensaje<input value={f.cuerpo} onChange={(e) => setF({ ...f, cuerpo: e.target.value })} maxLength={4000} required /></label>
        <label>Tipo
          <select value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })}>
            {Object.entries(CAT).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></label>
        <label className="chk"><input type="checkbox" checked={f.fijado} onChange={(e) => setF({ ...f, fijado: e.target.checked })} />Fijar arriba</label>
        <button className="btn">Publicar</button>
      </form>
      <Estado msg={msg} />{err && <p role="alert" className="aviso err">{err}</p>}
      {lista.length === 0 ? <p className="vacio">El muro está vacío.</p> : (
        <ul className="muro">{lista.map((c) => (
          <li key={c.id} className={`com-${c.categoria}`}>
            <b>{c.fijado ? "📌 " : ""}{c.titulo}</b> <small>{CAT[c.categoria]} · {fh(c.publicado_at)}</small>
            <p>{c.cuerpo}</p><button className="mini" onClick={() => retirar(c.id)}>Retirar</button>
          </li>))}</ul>)}
    </section>
  );
}

export function AvisosPago({ api }) {
  const [lista, recargar, err] = useLista(() => api.avisosPago(), [api.avisosPago]);
  const [msg, setMsg] = useState(null);
  const [tasa, setTasa] = useState("1.5");
  const resolver = async (a, aprobar) => {
    let motivo = "";
    if (!aprobar) { motivo = window.prompt("Motivo del rechazo") || ""; if (!motivo.trim()) return; }
    try { await api.resolverAviso(a.id, aprobar, motivo); setMsg({ ok: true, t: aprobar ? `Pago de ${clp(a.monto)} abonado al depto ${a.unidad}.` : "Aviso rechazado." }); await recargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const intereses = async () => {
    const periodo = new Date().toISOString().slice(0, 7);
    if (!window.confirm(`Cargar ${tasa}% de interés mensual a las unidades con deuda vencida (${periodo})?`)) return;
    try { const r = await api.cobrarIntereses({ tasa_mensual_pct: Number(tasa), periodo }); setMsg({ ok: true, t: `Intereses cargados a ${r.unidades} unidad(es), ${clp(r.total)} en total${r.ya_aplicados ? `; ${r.ya_aplicados} ya los tenían` : ""}.` }); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  return (
    <section aria-labelledby="h-av">
      <h3 id="h-av">Pagos avisados por transferencia</h3>
      <Estado msg={msg} />{err && <p role="alert" className="aviso err">{err}</p>}
      {lista.length === 0 ? <p className="vacio">Nadie ha avisado una transferencia.</p> : (
        <table className="tabla">
          <thead><tr><th>Depto</th><th className="der">Monto</th><th>Banco y operación</th><th>Estado</th><th /></tr></thead>
          <tbody>{lista.map((a) => (
            <tr key={a.id}>
              <td className="n">{a.unidad}</td><td className="der">{clp(a.monto)}</td>
              <td>{a.banco} · <code>{a.nro_operacion}</code></td><td>{a.estado}{a.motivo ? `: ${a.motivo}` : ""}</td>
              <td className="acc">{a.estado === "pendiente" && (<><button className="mini" onClick={() => resolver(a, true)}>Aprobar</button><button className="mini" onClick={() => resolver(a, false)}>Rechazar</button></>)}</td>
            </tr>))}</tbody>
        </table>)}
      <div className="envio">
        <label>Interés mensual por mora (%)<input type="number" min="0.1" max="10" step="0.1" value={tasa} onChange={(e) => setTasa(e.target.value)} /></label>
        <button className="btn sec" onClick={intereses} disabled={!(Number(tasa) > 0)}>Cargar intereses del mes</button>
      </div>
    </section>
  );
}

export default function Comunidad({ api, data, esAdmin }) {
  return (
    <div className="comunidad-vista">
      <header className="vista-cab"><h2>Conserjería y comunidad</h2>
        <p>Paquetes que llegan a recepción{esAdmin ? ", muro de avisos oficiales y transferencias que los residentes informan." : "."}</p></header>
      <Encomiendas api={api} data={data} />
      {esAdmin && <Comunicados api={api} />}
      {esAdmin && <AvisosPago api={api} />}
    </div>
  );
}
