"use client";
import { useCallback, useEffect, useState } from "react";
import { clp } from "../../lib/api";

const fh = (iso) => (iso ? new Date(iso).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");
const DESGLOSE = [["cuota_base", "Cuota base (por alícuota)"], ["agua", "Agua caliente y calefacción"], ["fondo_reserva", "Fondo de reserva"], ["intereses_multas", "Intereses y multas"], ["otros", "Otros cargos"]];

// Portal del residente: sólo lee y avisa; todo lo que muestra viene de /mi-depto (limitado a su unidad).
export default function MiDepto({ api, nombre, onSalir }) {
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");
  const [f, setF] = useState({ monto: "", banco: "", nro_operacion: "", fecha_transferencia: new Date().toISOString().slice(0, 10) });
  const [msg, setMsg] = useState(null);
  const cargar = useCallback(async () => {
    try { setD(await api.miDepto()); setErr(""); } catch (e) { if (e.status === 401) onSalir(); else setErr(e.message); }
  }, [api.miDepto]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { cargar(); const t = setInterval(cargar, 15000); return () => clearInterval(t); }, [cargar]);

  const avisar = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.avisarPago({ ...f, monto: Number(f.monto) }); setF({ ...f, monto: "", nro_operacion: "" }); setMsg({ ok: true, t: "Aviso enviado. El administrador lo revisará." }); await cargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const compartir = async (v) => {
    try { const r = await api.compartirVisita(v.id); window.open(r.url, "_blank", "noopener"); } catch (x) { setMsg({ ok: false, t: x.message }); }
  };

  if (!d) return <main className="cargando">{err || "Abriendo su departamento…"}</main>;
  const c = d.cuenta;
  return (
    <div className="shell">
      <header className="cab">
        <div className="marca"><b>Depto {d.unidad.numero}</b><span>{nombre || "Residente"}</span></div>
        <span />
        <button className="salir" onClick={onSalir}>Salir</button>
      </header>
      <main className="vista mi-depto">
        {err && <p role="alert" className="banda">{err}</p>}
        <header className="vista-cab"><h2>Mi depto</h2>
          <p className={c.estado === "al_dia" ? "estado-ok" : "estado-mora"}>
            {c.estado === "al_dia" ? (c.deuda > 0 ? `Al día. Próximo pago: ${clp(c.deuda)}.` : "Al día, sin saldo pendiente.") : `Moroso: debe ${clp(c.deuda)}, de los cuales ${clp(c.vencida)} están vencidos.`}
          </p></header>

        <section aria-labelledby="h-cuenta"><h3 id="h-cuenta">Gastos comunes</h3>
          <table className="tabla"><tbody>
            {DESGLOSE.filter(([k]) => c.desglose[k] > 0).map(([k, t]) => <tr key={k}><td>{t}</td><td className="der">{clp(c.desglose[k])}</td></tr>)}
            <tr><th>Total a pagar</th><th className="der">{clp(c.deuda)}</th></tr>
          </tbody></table>
          <p className="nota">Para transferir, indique el código <code>{d.unidad.codigo_cobro}</code> en el comentario.</p>
        </section>

        <section aria-labelledby="h-aviso"><h3 id="h-aviso">Avisar una transferencia</h3>
          <form className="envio" onSubmit={avisar}>
            <label>Monto<input type="number" min="1" step="1" value={f.monto} onChange={(e) => setF({ ...f, monto: e.target.value })} required /></label>
            <label>Banco<input value={f.banco} onChange={(e) => setF({ ...f, banco: e.target.value })} minLength={2} maxLength={60} required /></label>
            <label>N.º de operación<input value={f.nro_operacion} onChange={(e) => setF({ ...f, nro_operacion: e.target.value })} pattern="[A-Za-z0-9\-]{3,40}" required /></label>
            <label>Fecha<input type="date" max={new Date().toISOString().slice(0, 10)} value={f.fecha_transferencia} onChange={(e) => setF({ ...f, fecha_transferencia: e.target.value })} required /></label>
            <button className="btn">Avisar pago</button>
          </form>
          {msg && <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>}
          {d.avisos_pago.length > 0 && <ul className="muro">{d.avisos_pago.map((a) => <li key={a.id}>{clp(a.monto)} · {a.banco} · <code>{a.nro_operacion}</code> — {a.estado}{a.motivo ? `: ${a.motivo}` : ""}</li>)}</ul>}
        </section>

        <section aria-labelledby="h-paq"><h3 id="h-paq">Encomiendas por retirar ({d.encomiendas_pendientes.length})</h3>
          {d.encomiendas_pendientes.length === 0 ? <p className="vacio">No tiene paquetes en recepción.</p> :
            <ul className="muro">{d.encomiendas_pendientes.map((e) => <li key={e.id}>📦 {e.transportista || "Encomienda"} · llegó {fh(e.recibida_at)}{e.descripcion ? ` · ${e.descripcion}` : ""}</li>)}</ul>}
        </section>

        <section aria-labelledby="h-veh"><h3 id="h-veh">Mis vehículos y tags</h3>
          {d.vehiculos.length === 0 && d.tags.length === 0 ? <p className="vacio">No tiene vehículos ni tags autorizados.</p> : (<ul className="muro">
            {d.vehiculos.map((v) => <li key={v.id}><code>{v.patente}</code> {v.descripcion} {v.sticker ? "· con sticker" : ""}</li>)}
            {d.tags.map((t) => <li key={t.id}>Tag <code>{t.uid}</code> ({t.tipo}) — {t.estado}{t.patente ? ` · ${t.patente}` : ""}</li>)}
          </ul>)}
        </section>

        <section aria-labelledby="h-vis"><h3 id="h-vis">Mis visitas</h3>
          {d.visitas_activas.length === 0 ? <p className="vacio">No tiene pases vigentes.</p> : (<ul className="muro">
            {d.visitas_activas.map((v) => <li key={v.id}><b>{v.nombre}</b> · {fh(v.desde)} a {fh(v.hasta)} {v.patente && <code>{v.patente}</code>} <button className="mini" onClick={() => compartir(v)}>Enviar por WhatsApp</button></li>)}
          </ul>)}
        </section>

        <section aria-labelledby="h-muro"><h3 id="h-muro">Comunicados</h3>
          {d.comunicados.length === 0 ? <p className="vacio">No hay avisos vigentes.</p> : (<ul className="muro">
            {d.comunicados.map((m) => <li key={m.id} className={`com-${m.categoria}`}><b>{m.fijado ? "📌 " : ""}{m.titulo}</b> <small>{fh(m.publicado_at)}</small><p>{m.cuerpo}</p></li>)}
          </ul>)}
        </section>
      </main>
    </div>
  );
}
