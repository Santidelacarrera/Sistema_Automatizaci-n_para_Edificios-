"use client";
import { useEffect, useState } from "react";
import { clp, operarGlobal } from "../../lib/api";
import { Estado } from "./ui";

export default function Comercial({ sess, edificios }) {
  const [datos, setDatos] = useState(null), [msg, setMsg] = useState(null), [busy, setBusy] = useState(false);
  const [tab, setTab] = useState("contratos"), [ticket, setTicket] = useState(null);
  const req = (m, p, b) => operarGlobal(sess, m, p, b);
  async function cargar() {
    const rutas = ["clientes", "planes", "suscripciones", "cobros", "soporte", "metricas"];
    const resultados = await Promise.all(rutas.map((r) => req("GET", `/saas/${r}`)));
    setDatos(Object.fromEntries(rutas.map((r, i) => [r, resultados[i]])));
  }
  useEffect(() => { cargar().catch((e) => setMsg({ ok: false, t: e.message })); }, [sess.token]); // eslint-disable-line react-hooks/exhaustive-deps
  async function accion(fn) {
    if (busy) return;
    setBusy(true); setMsg(null);
    try { await fn(); await cargar(); setMsg({ ok: true, t: "Cambios guardados." }); }
    catch (e) { setMsg({ ok: false, t: e.message }); } finally { setBusy(false); }
  }
  const form = (fn) => (e) => { e.preventDefault(); const d = Object.fromEntries(new FormData(e.currentTarget)); accion(() => fn(d)); };
  return <section className="gestion-comunidad" aria-label="Administración SaaS">
    <header className="vista-cab"><h2>Administración SaaS</h2><p>Clientes, contratos y atención de las comunidades.</p></header>
    <nav className="gestion-tabs" aria-label="Gestión comercial">{[["contratos", "Clientes y planes"], ["suscripciones", "Suscripciones"], ["cobros", "Cobros SaaS"], ["soporte", "Soporte"]].map(([id, n]) =>
      <button key={id} className={`tab ${tab === id ? "on" : ""}`} onClick={() => { setTab(id); setMsg(null); }}>{n}</button>)}</nav>
    <Estado msg={msg} />
    {!datos && <p role="status">Cargando gestión comercial…</p>}
    {datos && <>
      <p>{datos.metricas.clientes} clientes · {datos.metricas.edificios} edificios · Ingreso mensual contratado: {clp(datos.metricas.ingreso_mensual_contratado)} · {datos.metricas.tickets_abiertos} solicitudes abiertas.</p>
      {tab === "contratos" && <>
        <section className="gestion-card"><h3>Registrar cliente</h3><form className="gestion-form" onSubmit={form((d) => req("POST", "/saas/clientes", d))}>
          <label>Nombre del cliente<input name="nombre" minLength={2} maxLength={160} required /></label>
          <label>RUT del cliente<input name="rut" maxLength={15} required /></label>
          <label>Correo de contacto<input name="contacto" type="email" maxLength={160} required /></label>
          <button className="btn" disabled={busy}>Registrar cliente</button></form>
          <ul className="items">{datos.clientes.map((c) => <li key={c.id}>{c.nombre} · {c.rut} · {c.contacto}</li>)}</ul></section>
        <section className="gestion-card"><h3>Nuevo plan</h3><p>Para cambiar condiciones de un contrato, cree un plan y asígnelo a la suscripción.</p>
          <form className="gestion-form" onSubmit={form((d) => req("POST", "/saas/planes", { ...d, max_unidades: Number(d.max_unidades), max_residentes: Number(d.max_residentes), max_dispositivos: Number(d.max_dispositivos) }))}>
            <label>Nombre del plan<input name="nombre" minLength={3} maxLength={100} required /></label>
            <label>Precio mensual (CLP)<input name="precio_mensual" type="number" step="0.01" min="0" required /></label>
            <label>Máximo de unidades<input name="max_unidades" type="number" min="1" max="100000" required /></label>
            <label>Máximo de residentes<input name="max_residentes" type="number" min="1" max="1000000" required /></label>
            <label>Máximo de dispositivos<input name="max_dispositivos" type="number" min="0" max="10000" required /></label>
            <button className="btn" disabled={busy}>Crear plan</button></form>
          <ul className="items">{datos.planes.map((p) => <li key={p.id}><b>{p.nombre}</b> · {clp(p.precio_mensual)} / mes · {p.max_unidades} unidades · {p.max_residentes} residentes · {p.max_dispositivos} dispositivos
            <button className="mini" disabled={busy} onClick={() => accion(() => req("PATCH", `/saas/planes/${p.id}`, { activo: !p.activo }))}>{p.activo ? "Retirar de nuevas contrataciones" : "Habilitar contrataciones"}</button></li>)}</ul></section>
      </>}
      {tab === "suscripciones" && <>
        <section className="gestion-card"><h3>Asignar o renovar contrato</h3><form className="gestion-form" onSubmit={form(({ edificio_id, ...d }) => {
          const sub = datos.suscripciones.find((s) => s.edificio_id === edificio_id);
          return req("PUT", `/saas/suscripciones/${encodeURIComponent(edificio_id)}`, { ...d, cliente_id: Number(d.cliente_id), plan_id: Number(d.plan_id), version: sub?.contrato?.version || 0 });
        })}>
          <label>Edificio del contrato<select name="edificio_id" required><option value="">Seleccione</option>{edificios.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}</select></label>
          <label>Cliente del contrato<select name="cliente_id" required><option value="">Seleccione</option>{datos.clientes.map((c) => <option key={c.id} value={c.id}>{c.nombre}</option>)}</select></label>
          <label>Plan contratado<select name="plan_id" required><option value="">Seleccione</option>{datos.planes.filter((p) => p.activo).map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}</select></label>
          <label>Estado del contrato<select name="estado"><option value="prueba">Prueba</option><option value="activa">Activa</option><option value="suspendida">Suspendida</option><option value="cancelada">Cancelada</option></select></label>
          <label>Vigente hasta<input name="vigente_hasta" type="date" required /></label><label>Motivo del contrato<textarea name="motivo" minLength={10} maxLength={500} required /></label>
          <p>Al vencer, suspender o cancelar se impiden nuevas altas. Los registros y accesos existentes se conservan.</p><button className="btn" disabled={busy}>Guardar contrato</button></form></section>
        <ul className="items">{datos.suscripciones.map((s) => <li key={s.edificio_id}><b>{s.edificio_id}</b> · {s.plan?.nombre || "Sin contrato asignado"} · {s.contrato ? `${s.contrato.estado} hasta ${s.contrato.vigente_hasta}` : "Instalación sin cuotas comerciales"}
          <p>Uso: {s.uso.unidades} unidades · {s.uso.residentes} residentes · {s.uso.dispositivos} dispositivos</p></li>)}</ul>
      </>}
      {tab === "cobros" && <>
        <p>Registro interno de cuotas SaaS. Los cobros no se ejecutan automáticamente y estos registros no son documentos tributarios.</p>
        <section className="gestion-card"><h3>Emitir cuota mensual</h3><form className="gestion-form" onSubmit={form(({ edificio_id, ...d }) => req("POST", `/saas/suscripciones/${encodeURIComponent(edificio_id)}/cobros`, d))}>
          <label>Edificio a cobrar<select name="edificio_id" required><option value="">Seleccione</option>{datos.suscripciones.filter((s) => s.vigente && s.contrato.estado === "activa").map((s) => <option key={s.edificio_id}>{s.edificio_id}</option>)}</select></label>
          <label>Período del cobro<input name="periodo" type="month" required /></label><label>Vencimiento del cobro<input name="vencimiento" type="date" required /></label>
          <button className="btn" disabled={busy}>Emitir cuota interna</button></form></section>
        <ul className="items">{datos.cobros.map((c) => <li key={c.id}><b>{c.edificio_id} · {c.periodo} · {clp(c.monto)}</b> · {c.estado} · {c.referencia}
          {c.estado === "pendiente" && <details><summary>Registrar pago o anulación</summary><form className="gestion-form" onSubmit={form((d) => req("POST", `/saas/cobros/${c.id}/resolver`, d))}>
            <label>Resolución de cuota<select name="estado"><option value="pagado">Pago recibido y verificado</option><option value="anulado">Anular</option></select></label>
            <label>Referencia de verificación<input name="referencia" minLength={3} maxLength={120} required /></label>
            <label>Motivo de resolución<textarea name="motivo" minLength={10} maxLength={500} required /></label><button className="btn" disabled={busy}>Confirmar resolución</button></form></details>}</li>)}</ul>
      </>}
      {tab === "soporte" && <>
        {datos.soporte.length === 0 && <p className="vacio">No hay solicitudes de soporte.</p>}
        <ul className="items">{datos.soporte.map((t) => <li key={t.id}><button className="mini" disabled={busy} onClick={() => accion(async () => setTicket(await req("GET", `/edificios/${t.edificio_id}/soporte/${t.id}`)))}>{t.titulo}</button> · {t.edificio_id} · {t.estado}</li>)}</ul>
        {ticket && <section className="gestion-card"><h3>{ticket.titulo}</h3><ul className="items">{ticket.mensajes.map((m) => <li key={m.id}>{m.texto}</li>)}</ul>
          <form className="gestion-form" onSubmit={form(async (d) => { await req("POST", `/edificios/${ticket.edificio_id}/soporte/${ticket.id}/mensajes`, d); setTicket(await req("GET", `/edificios/${ticket.edificio_id}/soporte/${ticket.id}`)); })}>
            <label>Respuesta de soporte<textarea name="texto" minLength={3} maxLength={6000} required /></label><label>Estado de atención<select name="estado" defaultValue={ticket.estado}><option value="abierto">Abierto</option><option value="en_progreso">En progreso</option><option value="resuelto">Resuelto</option></select></label>
            <button className="btn" disabled={busy}>Enviar respuesta</button></form></section>}
      </>}
    </>}
  </section>;
}
