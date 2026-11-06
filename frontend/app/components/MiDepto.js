"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { clp } from "../../lib/api";
import { Confirmar, Estado, fh, hoyISO } from "./ui";
import Icono from "./Icono";

const DESGLOSE = [["cuota_base", "Cuota base, según su alícuota"], ["agua", "Agua caliente y calefacción"], ["fondo_reserva", "Aporte al fondo de reserva"], ["intereses_multas", "Intereses y multas"], ["otros", "Otros cargos (reservas)"]];

function Visitas({ api, d, recargar, unidadId }) {
  const vacio = { nombre_visita: "", desde: "", hasta: "", patente: "", usa_estacionamiento: true };
  const [f, setF] = useState(vacio);
  const [cupos, setCupos] = useState(null);
  const [msg, setMsg] = useState(null);
  const [qr, setQr] = useState({}); // id -> object URL
  const [wa, setWa] = useState(null); // visita cuyo pase se está enviando
  const [tel, setTel] = useState("");
  const urls = useRef([]);
  useEffect(() => { api.cupos().then(setCupos).catch(() => {}); return () => urls.current.forEach(URL.revokeObjectURL); }, [api.cupos, d.visitas_activas.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const crear = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.reservarVisita({ ...f, unidad_id: unidadId, desde: f.desde, hasta: f.hasta }); setF(vacio); setMsg({ ok: true, t: "Pase creado. Envíelo a su visita por WhatsApp." }); await recargar(); }
    catch (x) { setMsg({ ok: false, t: typeof x.detail === "string" ? x.detail : x.message }); }
  };
  const verQr = async (id) => {
    if (qr[id] !== undefined) { setQr((q) => { const n = { ...q }; delete n[id]; return n; }); return; }
    try { const u = await api.qrVisita(id); if (u) urls.current.push(u); setQr((q) => ({ ...q, [id]: u })); } catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const enviar = async () => {
    try { const r = await api.compartirVisita(wa.id, tel); window.open(r.url, "_blank", "noopener"); setWa(null); setTel(""); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  return (
    <section aria-labelledby="h-vis">
      <h3 id="h-vis">Mis visitas</h3>
      {cupos && <p className="nota">{cupos.libres === 0 ? "No quedan estacionamientos de visita libres en este momento." : `${cupos.libres} de ${cupos.total} estacionamientos de visita libres ahora.`} Si su visita no llega en el plazo, el cupo se libera solo.</p>}
      <form className="fila-form" onSubmit={crear}>
        <label className="ancho">Nombre de la visita<input value={f.nombre_visita} onChange={(e) => setF({ ...f, nombre_visita: e.target.value })} maxLength={120} required /></label>
        <label>Desde<input type="datetime-local" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} required /></label>
        <label>Hasta<input type="datetime-local" value={f.hasta} min={f.desde} onChange={(e) => setF({ ...f, hasta: e.target.value })} required /></label>
        <label>Patente<input value={f.patente} onChange={(e) => setF({ ...f, patente: e.target.value.toUpperCase() })} maxLength={8} placeholder="BBCD12" disabled={!f.usa_estacionamiento} /></label>
        <label className="chk"><input type="checkbox" checked={f.usa_estacionamiento} onChange={(e) => setF({ ...f, usa_estacionamiento: e.target.checked })} />Llega en auto y necesita estacionamiento</label>
        <button className="btn">Crear pase</button>
      </form>
      <Estado msg={msg} />
      {d.visitas_activas.length === 0 ? <p className="vacio">No tiene pases vigentes. Cree uno arriba y envíelo por WhatsApp.</p> : (
        <ul className="items">{d.visitas_activas.map((v) => (
          <li key={v.id}>
            <div className="items-cab"><b>{v.nombre}</b><span>{v.patente && <code>{v.patente}</code>}</span><time>{fh(v.desde)} a {fh(v.hasta)}</time></div>
            <div className="acc">
              <button className="mini con-icono" onClick={() => { setWa(v); setTel(""); }}><Icono n="whatsapp" />Enviar por WhatsApp</button>
              <button className="mini" onClick={() => verQr(v.id)}>{qr[v.id] !== undefined ? "Ocultar código QR" : "Ver código QR"}</button>
            </div>
            {qr[v.id] ? <img className="qr" src={qr[v.id]} alt={`Código QR del pase de ${v.nombre}`} width="160" height="160" /> : qr[v.id] === null ? <p className="nota">El código QR se muestra al conectar con el servidor.</p> : null}
          </li>))}</ul>)}
      {wa && (
        <Confirmar pregunta={`WhatsApp de ${wa.nombre} (opcional):`} etiqueta="Abrir WhatsApp" onConfirmar={enviar} onCancelar={() => setWa(null)}>
          <input aria-label="Teléfono de la visita" type="tel" inputMode="tel" value={tel} onChange={(e) => setTel(e.target.value)} placeholder="+56 9 1234 5678" autoFocus />
        </Confirmar>)}
    </section>
  );
}

function Reservar({ api, recargar, unidadId }) {
  const [espacios, setEspacios] = useState([]);
  const [f, setF] = useState({ espacio_id: "", fecha: hoyISO(), desde: "", hasta: "", asistentes: "" });
  const [dia, setDia] = useState(null);
  const [msg, setMsg] = useState(null);
  useEffect(() => { api.espaciosComunes().then(setEspacios).catch(() => {}); }, [api.espaciosComunes]); // eslint-disable-line react-hooks/exhaustive-deps
  const esp = espacios.find((e) => String(e.id) === String(f.espacio_id));
  const cargarDia = useCallback(async () => {
    if (!f.espacio_id || !f.fecha) { setDia(null); return; }
    try { setDia(await api.disponibilidad(f.espacio_id, f.fecha)); } catch { setDia(null); }
  }, [f.espacio_id, f.fecha]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { cargarDia(); }, [cargarDia]);

  const reservar = async (e) => {
    e.preventDefault(); setMsg(null);
    try {
      const r = await api.reservarEspacio({ espacio_id: Number(f.espacio_id), unidad_id: unidadId, desde: `${f.fecha}T${f.desde}`, hasta: `${f.fecha}T${f.hasta}`, asistentes: Number(f.asistentes) || 0 });
      setMsg({ ok: true, t: r.tarifa > 0 ? `Reserva confirmada. Se cargaron ${clp(r.tarifa)} a su gasto común.` : "Reserva confirmada." });
      await Promise.all([cargarDia(), recargar()]);
    } catch (x) { setMsg({ ok: false, t: x.detail?.motivos ? x.detail.motivos.join(" ") : x.message }); }
  };
  if (espacios.length === 0) return null;
  return (
    <section aria-labelledby="h-res">
      <h3 id="h-res">Reservar un espacio común</h3>
      <form className="fila-form" onSubmit={reservar}>
        <label>Espacio
          <select value={f.espacio_id} onChange={(e) => setF({ ...f, espacio_id: e.target.value })} required>
            <option value="">Elegir</option>{espacios.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}</select></label>
        <label>Día<input type="date" min={hoyISO()} value={f.fecha} onChange={(e) => setF({ ...f, fecha: e.target.value })} required /></label>
        <label>Desde<input type="time" value={f.desde} onChange={(e) => setF({ ...f, desde: e.target.value })} required /></label>
        <label>Hasta<input type="time" value={f.hasta} onChange={(e) => setF({ ...f, hasta: e.target.value })} required /></label>
        <label>Personas<input type="number" min="1" max={esp?.aforo || 1000} value={f.asistentes} onChange={(e) => setF({ ...f, asistentes: e.target.value })} required /></label>
        <button className="btn" disabled={!f.espacio_id}>Reservar</button>
      </form>
      {esp && <p className="nota">{esp.tarifa ? `Uso: ${clp(esp.tarifa)}, se suma al gasto común. ` : "Sin costo de uso. "}{esp.aforo ? `Máximo ${esp.aforo} personas. ` : ""}{esp.horario ? `Horario permitido: ${esp.horario.desde} a ${esp.horario.hasta}.` : ""}</p>}
      {dia && (dia.abierto === false ? <p className="vacio">Ese día el espacio no está disponible según el reglamento.</p> : dia.ocupadas.length === 0 ? <p className="nota">El {f.fecha.split("-").reverse().join("-")} está libre todo el día.</p> : (
        <div className="nota"><p>Ya reservado ese día:</p><ul className="franjas">{dia.ocupadas.map((o, i) => <li key={i}>{fh(o.desde)} a {fh(o.hasta).slice(-5)}</li>)}</ul></div>))}
      <Estado msg={msg} />
    </section>
  );
}

// Portal del residente: todo viene de /mi-depto, limitado a su unidad.
export default function MiDepto({ api, nombre, onSalir, unidadId, embebido = false }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ monto: "", banco: "", nro_operacion: "", fecha_transferencia: hoyISO() });
  const [msg, setMsg] = useState(null);
  const apiRef = useRef(api);
  apiRef.current = api;
  const cargar = useCallback(async () => {
    try { setD(await apiRef.current.miDepto(unidadId)); setErr(""); } catch (e) { if (e.status === 401) onSalir(); else setErr(e.message); }
  }, [unidadId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { cargar(); const t = setInterval(cargar, 20000); return () => clearInterval(t); }, [cargar]);

  const avisar = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.avisarPago({ ...f, unidad_id: unidadId, monto: Number(f.monto) }); setF({ ...f, monto: "", nro_operacion: "" }); setMsg({ ok: true, t: "Aviso enviado. El administrador lo revisa y abona el pago." }); await cargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };

  if (!d) return <main className="cargando">{err || "Abriendo su departamento…"}</main>;
  const c = d.cuenta;
  const contenido = (
    <>
        {err && <p role="alert" className="banda">{err}</p>}
        <header className="vista-cab"><h2>Mi depto</h2>
          <p className={c.estado === "al_dia" ? "estado-ok" : "estado-mora"}>
            {c.estado === "al_dia" ? (c.deuda > 0 ? `Al día. Su próximo pago es de ${clp(c.deuda)}.` : "Al día, sin saldo pendiente.") : `Con deuda vencida: ${clp(c.vencida)} de un total de ${clp(c.deuda)}.`}
          </p></header>

        <section aria-labelledby="h-cuenta">
          <h3 id="h-cuenta">Gastos comunes</h3>
          {c.deuda === 0 ? <p className="vacio">No tiene cargos pendientes.</p> : (
            <table className="tabla"><tbody>
              {DESGLOSE.filter(([k]) => c.desglose[k] > 0).map(([k, t]) => <tr key={k}><td>{t}</td><td className="der">{clp(c.desglose[k])}</td></tr>)}
            </tbody><tfoot><tr><th>Total a pagar</th><th className="der">{clp(c.deuda)}</th></tr></tfoot></table>)}
          <p className="nota">Al transferir, escriba el código <code>{d.unidad.codigo_cobro}</code> en el comentario para que se asigne solo.</p>
        </section>

        <section aria-labelledby="h-aviso">
          <h3 id="h-aviso">Ya transferí: avisar el pago</h3>
          <form className="fila-form" onSubmit={avisar}>
            <label>Monto (CLP)<input type="number" min="1" step="1" value={f.monto} onChange={(e) => setF({ ...f, monto: e.target.value })} required /></label>
            <label>Banco<input value={f.banco} onChange={(e) => setF({ ...f, banco: e.target.value })} minLength={2} maxLength={60} required /></label>
            <label>N.º de operación<input value={f.nro_operacion} onChange={(e) => setF({ ...f, nro_operacion: e.target.value })} pattern="[A-Za-z0-9\-]{3,40}" title="Letras, números y guiones" required /></label>
            <label>Fecha<input type="date" max={hoyISO()} value={f.fecha_transferencia} onChange={(e) => setF({ ...f, fecha_transferencia: e.target.value })} required /></label>
            <button className="btn">Avisar pago</button>
          </form>
          <Estado msg={msg} />
          {d.avisos_pago.length > 0 && <ul className="items compacta">{d.avisos_pago.map((a) => <li key={a.id}>{clp(a.monto)} · {a.banco} · operación {a.nro_operacion} <span className={`etq etq-${a.estado}`}>{{ pendiente: "Por revisar", aprobado: "Abonado", rechazado: "Rechazado" }[a.estado]}</span>{a.motivo ? ` — ${a.motivo}` : ""}</li>)}</ul>}
        </section>

        <section aria-labelledby="h-paq">
          <h3 id="h-paq">Encomiendas en recepción</h3>
          {d.encomiendas_pendientes.length === 0 ? <p className="vacio">No tiene paquetes por retirar.</p> :
            <ul className="items compacta">{d.encomiendas_pendientes.map((e) => <li key={e.id}><span className="con-icono"><Icono n="paquete" />{e.transportista || "Encomienda"}</span> llegó el {fh(e.recibida_at)}{e.descripcion ? ` · ${e.descripcion}` : ""}</li>)}</ul>}
        </section>

        <Visitas api={api} d={d} recargar={cargar} unidadId={unidadId} />
        <Reservar api={api} recargar={cargar} unidadId={unidadId} />

        <section aria-labelledby="h-veh">
          <h3 id="h-veh">Mis vehículos y tags</h3>
          {d.vehiculos.length === 0 && d.tags.length === 0 ? <p className="vacio">No tiene vehículos ni tags autorizados. Pídale al administrador que los registre.</p> : (
            <ul className="items compacta">
              {d.vehiculos.map((v) => <li key={v.id}><code>{v.patente}</code> {v.descripcion}{v.sticker ? " · con sticker" : ""}</li>)}
              {d.tags.map((t) => <li key={t.id}>Tag <code>{t.uid}</code> ({t.tipo}): {t.estado}{t.patente ? ` · ${t.patente}` : ""}</li>)}
            </ul>)}
        </section>

        <section aria-labelledby="h-muro">
          <h3 id="h-muro">Comunicados de la comunidad</h3>
          {d.comunicados.length === 0 ? <p className="vacio">No hay avisos vigentes.</p> : (
            <ul className="items">{d.comunicados.map((m) => (
              <li key={m.id}><div className="items-cab"><b>{m.fijado ? <Icono n="fijar" titulo="Fijado" /> : null} {m.titulo}</b><time>{fh(m.publicado_at)}</time></div><p>{m.cuerpo}</p></li>))}</ul>)}
        </section>
    </>
  );
  if (embebido) return <div className="seccion-vista mi-depto">{contenido}</div>;
  return (
    <div className="shell">
      <header className="cab">
        <div className="marca"><b>Depto {d.unidad.numero}</b><span>{nombre || "Residente"}</span></div>
        <button className="salir" onClick={onSalir}>Salir</button>
      </header>
      <main className="vista seccion-vista mi-depto">{contenido}</main>
    </div>
  );
}
