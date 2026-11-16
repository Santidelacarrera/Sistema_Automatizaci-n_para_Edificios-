"use client";
import { useEffect, useRef, useState } from "react";
import { clp } from "../../lib/api";
import { Estado, fh } from "./ui";
import Dispositivos from "./Dispositivos";

const TITULOS = { resumen: "Resumen", incidencias: "Incidencias", proveedores: "Proveedores y mantenimiento", asambleas: "Asambleas", documentos: "Documentos", notificaciones: "Notificaciones", automatizaciones: "Automatizaciones", dispositivos: "Dispositivos", soporte: "Soporte", suscripcion: "Mi suscripción" };
const CAMINOS = { resumen: "/dashboard", incidencias: "/incidencias", proveedores: "/proveedores", asambleas: "/asambleas", documentos: "/documentos", notificaciones: "/notificaciones", automatizaciones: "/automatizaciones", dispositivos: "/dispositivos", soporte: "/soporte", suscripcion: "/suscripcion" };
const datosForm = (e) => Object.fromEntries(new FormData(e.currentTarget));

export default function Operaciones({ api, esAdmin }) {
  const [tab, setTab] = useState(esAdmin ? "resumen" : "incidencias");
  const [datos, setDatos] = useState(null);
  const [detalle, setDetalle] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [proveedores, setProveedores] = useState([]);
  const [planes, setPlanes] = useState([]);
  const [pagos, setPagos] = useState([]);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const [fuentes, setFuentes] = useState([]);
  const [respuesta, setRespuesta] = useState(null);
  const [reversa, setReversa] = useState(null);
  const apiRef = useRef(api); apiRef.current = api;
  const secuencia = useRef(0);
  const request = (m, p, b) => apiRef.current.operar(m, p, b);
  const cargar = async (seccion = tab) => {
    const ticket = ++secuencia.current;
    try {
      const result = await request("GET", CAMINOS[seccion]);
      if (ticket === secuencia.current) setDatos(result);
    } catch (e) { if (ticket === secuencia.current) setMsg({ ok: false, t: e.message }); }
  };
  useEffect(() => { setDatos(null); setDetalle(null); setMsg(null); cargar(tab); return () => { secuencia.current++; }; }, [tab]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!esAdmin) return;
    Promise.all([request("GET", "/residentes"), request("GET", "/proveedores"), request("GET", "/mantenimientos")])
      .then(([r, p, m]) => { setPersonas(r); setProveedores(p); setPlanes(m); }).catch((e) => setMsg({ ok: false, t: e.message }));
  }, [esAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

  const accion = async (fn, texto = "Cambios guardados.") => {
    if (busy) return;
    setBusy(true); setMsg(null);
    try { const r = await fn(); setMsg({ ok: true, t: texto }); await cargar(); return r; }
    catch (e) { setMsg({ ok: false, t: e.message }); return null; }
    finally { setBusy(false); }
  };
  const abrir = async (id, conservarMensaje = false) => {
    setBusy(true); if (!conservarMensaje) setMsg(null);
    try { setDetalle(await request("GET", `${CAMINOS[tab]}/${id}`)); }
    catch (e) { setMsg({ ok: false, t: e.message }); } finally { setBusy(false); }
  };
  const enviar = (ruta, transformar = (d) => d, despues) => async (e) => {
    e.preventDefault(); const f = e.currentTarget; const body = transformar(datosForm(e));
    const result = await accion(() => request("POST", ruta, body));
    if (result) { f.reset(); if (despues) await despues(result); }
  };
  const personal = personas.filter((r) => r.activo && ["admin", "conserje"].includes(r.rol));
  const opcionesPersonal = personal.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>);

  return <section className="gestion-comunidad" aria-label="Gestión comunitaria">
    <header className="vista-cab"><h2>Gestión comunitaria</h2><p>Seguimiento, acuerdos y documentos de su comunidad.</p></header>
    <nav className="gestion-tabs" aria-label="Módulos de comunidad">
      {Object.entries(TITULOS).filter(([k]) => esAdmin || !["resumen", "proveedores", "automatizaciones", "dispositivos", "soporte", "suscripcion"].includes(k)).map(([k, v]) =>
        <button key={k} className={`tab ${tab === k ? "on" : ""}`} aria-current={tab === k ? "page" : undefined} onClick={() => {
          if (k !== tab) { secuencia.current++; setDatos(null); setDetalle(null); setTab(k); }
        }}>{v}</button>)}
    </nav>
    <Estado msg={msg} />
    {!datos && !msg && <p role="status">Cargando…</p>}
    {tab === "dispositivos" && esAdmin && <Dispositivos api={api} lista={datos} recargar={() => cargar()} />}

    {tab === "suscripcion" && esAdmin && datos && <section className="gestion-card"><h3>Contrato de la comunidad</h3>
      {datos.contrato ? <p>{datos.plan.nombre} · {datos.contrato.estado} · Vigencia: {datos.contrato.vigente_hasta} · {clp(datos.plan.precio_mensual)} / mes</p> : <p>Su comunidad todavía no tiene un contrato comercial asignado.</p>}
      <ul>{Object.entries(datos.uso).map(([k, v]) => <li key={k}>{k}: {v}{datos.plan && ` de ${datos.plan["max_" + k]}`}</li>)}</ul>
      <p>Para solicitar cambios o renovar su contrato, contacte con soporte.</p></section>}

    {tab === "soporte" && esAdmin && <>
      <section className="gestion-card"><h3>Contactar con soporte</h3><form className="gestion-form" onSubmit={enviar("/soporte")}>
        <label>Asunto de soporte<input name="titulo" minLength={3} maxLength={160} required /></label><label>Descripción de la solicitud<textarea name="texto" minLength={3} maxLength={6000} required /></label>
        <button className="btn" disabled={busy}>Enviar solicitud</button></form></section>
      {datos?.length === 0 && <p className="vacio">No hay solicitudes de soporte.</p>}
      <ul className="items">{datos?.map((t) => <li key={t.id}><button className="mini" onClick={() => abrir(t.id)}>{t.titulo}</button> · {t.estado}</li>)}</ul>
      {detalle && <section className="gestion-card"><h3>{detalle.titulo}</h3><ul className="items">{detalle.mensajes.map((m) => <li key={m.id}>{m.texto} <small>{fh(m.creado)}</small></li>)}</ul>
        <form className="gestion-form" onSubmit={enviar(`/soporte/${detalle.id}/mensajes`, undefined, () => abrir(detalle.id, true))}>
          <label>Mensaje a soporte<textarea name="texto" minLength={3} maxLength={6000} required /></label>
          <label>Estado de la solicitud<select name="estado"><option value="abierto">Abierta</option><option value="resuelto">Resuelta</option></select></label>
          <button className="btn" disabled={busy}>Actualizar solicitud</button></form></section>}
    </>}

    {tab === "resumen" && datos && <>
      <div className="gestion-indicadores">{Object.entries(datos).map(([k, v]) => <article key={k}><span>{({ unidades: "Unidades", residentes: "Residentes activos", ocupacion_pct: "Ocupación (%)", ingresos_mes: "Ingresos del mes", deuda: "Deuda total", saldo_favor: "Anticipos disponibles", deuda_vencida: "Deuda vencida", incidencias_abiertas: "Incidencias abiertas", incidencias_criticas: "Incidencias críticas", ordenes_pendientes: "Órdenes por aprobar", encomiendas_pendientes: "Paquetes por retirar" })[k]}</span><strong>{["ingresos_mes", "deuda", "saldo_favor", "deuda_vencida"].includes(k) ? clp(v) : v}</strong></article>)}</div>
      <section className="gestion-card"><h3>Registrar unidad</h3><form className="fila-form" onSubmit={enviar("/unidades", (d) => ({ ...d, coeficiente: Number(d.coeficiente), estacionamientos: Number(d.estacionamientos) }))}>
        <label>Número de unidad<input name="numero" required maxLength={20} /></label>
        <label>Coeficiente (0 a 1)<input name="coeficiente" type="number" step="0.000001" min="0.000001" max="1" required /></label>
        <label>Código de cobro<input name="codigo_cobro" maxLength={30} required /></label>
        <label>Estacionamientos<input name="estacionamientos" type="number" min="0" defaultValue="0" required /></label>
        <button className="btn" disabled={busy}>Registrar unidad</button>
      </form></section>
      <section className="gestion-card"><h3>Pagos y movimientos</h3>
        <button className="btn sec" disabled={busy} onClick={() => accion(async () => { setPagos(await request("GET", "/pagos")); }, "Pagos actualizados.")}>Consultar pagos</button>{" "}
        <button className="btn sec" disabled={busy} onClick={() => accion(() => api.descargar("/finanzas/exportar.csv", "movimientos.csv"), "Archivo descargado.")}>Exportar movimientos CSV</button>
        {pagos.length > 0 && <ul className="items">{pagos.map((p) => <li key={p.id}>{clp(p.monto)} · {p.fecha} · {p.referencia || p.ref_banco} · {p.revertido ? "Revertido" : "Registrado"}
          <button className="mini" disabled={busy} onClick={() => accion(() => api.descargar(`/pagos/${p.id}/comprobante.pdf`, `comprobante-${p.id}.pdf`), "Comprobante descargado.")}>Comprobante PDF</button>
          {!p.revertido && p.conciliado && <button className="mini" onClick={() => setReversa(p)}>Revertir pago {p.id}</button>}</li>)}</ul>}
        {reversa && <form className="confirmar" onSubmit={async (e) => {
          e.preventDefault(); const d = datosForm(e); const r = await accion(() => request("POST", `/pagos/${reversa.id}/revertir`, d));
          if (r) { setReversa(null); setPagos(await request("GET", "/pagos")); }
        }}><p>La reversa de {clp(reversa.monto)} restablecerá los cargos asociados y quedará auditada.</p>
          <label>Motivo de reversa<input name="motivo" minLength={10} maxLength={500} required /></label>
          <button className="btn peligro" disabled={busy}>Confirmar reversa</button><button type="button" className="btn sec" onClick={() => setReversa(null)}>Cancelar</button></form>}
      </section>
    </>}

    {tab === "incidencias" && <>
      <section className="gestion-card"><h3>Reportar una incidencia</h3>
        <form className="gestion-form" onSubmit={enviar("/incidencias")}>
          <label>Título de incidencia<input name="titulo" minLength={3} maxLength={160} required /></label>
          <label>Descripción<textarea name="descripcion" minLength={3} maxLength={6000} required /></label>
          <label>Prioridad<select name="prioridad" defaultValue="normal"><option value="baja">Baja</option><option value="normal">Normal</option><option value="alta">Alta</option><option value="critica">Crítica</option></select></label>
          <button className="btn" disabled={busy}>Enviar incidencia</button>
        </form></section>
      {datos?.length === 0 && <p className="vacio">No hay incidencias registradas.</p>}
      <ul className="items">{datos?.map((i) => <li key={i.id}><button className="mini" onClick={() => abrir(i.id)}>{i.titulo}</button><span className="etq">{i.estado.replaceAll("_", " ")}</span> · {i.prioridad}{i.vencimiento && ` · vence ${i.vencimiento}`}</li>)}</ul>
      {detalle && <section className="gestion-card" aria-label="Detalle de incidencia"><h3>{detalle.titulo}</h3><p>{detalle.descripcion}</p>
        {esAdmin && detalle.estado !== "cerrada" && <form className="fila-form" key={`${detalle.id}-${detalle.version}`} onSubmit={async (e) => {
          e.preventDefault(); const d = datosForm(e);
          const r = await accion(() => request("PATCH", `/incidencias/${detalle.id}`, { version: detalle.version, estado: d.estado,
            responsable_id: d.responsable_id ? Number(d.responsable_id) : null, vencimiento: d.vencimiento || null })); if (r) await abrir(detalle.id, true);
        }}><label htmlFor="incidencia-estado">Estado</label><select id="incidencia-estado" name="estado" defaultValue={detalle.estado}>{["abierta", "asignada", "en_progreso", "resuelta", "cerrada"].map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select>
          <label>Responsable<select name="responsable_id" defaultValue={detalle.responsable_id || ""}><option value="">Sin asignar</option>{opcionesPersonal}</select></label>
          <label>Vencimiento<input type="date" name="vencimiento" defaultValue={detalle.vencimiento || ""} /></label>
          <button className="btn" disabled={busy}>Guardar seguimiento</button></form>}
        <h4>Comentarios</h4><ul className="items">{detalle.comentarios.map((c) => <li key={c.id}>{c.texto} <small>{fh(c.creado)}</small></li>)}</ul>
        {detalle.estado !== "cerrada" && <form className="fila-form" onSubmit={enviar(`/incidencias/${detalle.id}/comentarios`, undefined, () => abrir(detalle.id))}>
          <label>Comentario<textarea name="texto" maxLength={4000} required /></label><button className="btn" disabled={busy}>Agregar comentario</button></form>}
        {esAdmin && !detalle.orden && !["cerrada", "resuelta"].includes(detalle.estado) && <>
          <h4>Orden de trabajo</h4><form className="gestion-form" onSubmit={enviar(`/incidencias/${detalle.id}/orden`, (d) => ({ ...d, proveedor_id: Number(d.proveedor_id) }), () => abrir(detalle.id))}>
            <label>Proveedor<select name="proveedor_id" required><option value="">Elegir proveedor</option>{proveedores.map((p) => <option key={p.id} value={p.id}>{p.nombre}</option>)}</select></label>
            <label>Trabajo a realizar<textarea name="detalle" minLength={3} maxLength={4000} required /></label>
            <label>Presupuesto (CLP)<input type="number" name="presupuesto" min="0" step="0.01" required /></label><button className="btn" disabled={busy}>Crear orden de trabajo</button>
          </form></>}
        {detalle.orden && <><h4>Orden #{detalle.orden.id} · {detalle.orden.estado}</h4><p>{detalle.orden.detalle} · {clp(detalle.orden.presupuesto)}</p>
          {!["terminada", "rechazada"].includes(detalle.orden.estado) && <form className="fila-form" onSubmit={enviar(`/ordenes-trabajo/${detalle.orden.id}/estado`, (d) => ({ estado: d.estado, evaluacion: d.evaluacion ? Number(d.evaluacion) : null }), () => abrir(detalle.id))}>
            <label>Acción sobre el trabajo<select name="estado">{({ pendiente: ["aprobada", "rechazada"], aprobada: ["en_progreso", "rechazada"], en_progreso: ["terminada"] }[detalle.orden.estado] || []).map((s) => <option key={s} value={s}>{s.replaceAll("_", " ")}</option>)}</select></label>
            {detalle.orden.estado === "en_progreso" && <label>Evaluación (1 a 5)<input name="evaluacion" type="number" min="1" max="5" /></label>}
            <button className="btn" disabled={busy}>Confirmar cambio de orden</button></form>}</>}
        <details><summary>Historial de cambios</summary><ul>{detalle.historial.map((h, i) => <li key={i}>{h.tipo} · {fh(h.creado)}</li>)}</ul></details>
      </section>}
    </>}

    {tab === "proveedores" && esAdmin && <>
      <section className="gestion-card"><h3>Registrar proveedor</h3><form className="gestion-form" onSubmit={enviar("/proveedores", (d) => ({ ...d, contrato_hasta: d.contrato_hasta || null }), async () => setProveedores(await request("GET", "/proveedores")))}>
        <label>Nombre del proveedor<input name="nombre" minLength={2} maxLength={120} required /></label>
        <label>RUT del proveedor<input name="rut" maxLength={15} required /></label>
        <label>Contacto<input name="contacto" maxLength={160} /></label><label>Servicios<input name="servicio" maxLength={160} /></label>
        <label>Fin de contrato<input type="date" name="contrato_hasta" /></label><button className="btn" disabled={busy}>Registrar proveedor</button>
      </form></section>
      <ul className="items">{datos?.map((p) => <li key={p.id}><b>{p.nombre}</b> · {p.rut} · {p.servicio}<p>{p.contacto}{p.contrato_hasta && ` · Contrato hasta ${p.contrato_hasta}`}</p></li>)}</ul>
      <section className="gestion-card"><h3>Mantenimiento preventivo</h3><form className="gestion-form" onSubmit={enviar("/mantenimientos", (d) => ({ ...d, responsable_id: Number(d.responsable_id), intervalo_dias: Number(d.intervalo_dias) }), async () => setPlanes(await request("GET", "/mantenimientos")))}>
        <label>Tarea de mantenimiento<input name="titulo" minLength={3} maxLength={160} required /></label>
        <label>Responsable del mantenimiento<select name="responsable_id" required><option value="">Elegir</option>{opcionesPersonal}</select></label>
        <label>Intervalo en días<input name="intervalo_dias" type="number" min="1" max="3650" defaultValue="30" required /></label>
        <label>Próxima revisión<input name="proxima_fecha" type="date" required /></label><button className="btn" disabled={busy}>Programar mantenimiento</button>
      </form><ul className="items">{planes.map((p) => <li key={p.id}>{p.titulo} · {p.proxima_fecha} · {p.activo ? "Activo" : "Pausado"}
        <button className="mini" disabled={busy} onClick={() => accion(async () => { await request("PATCH", `/mantenimientos/${p.id}`, { activo: !p.activo }); setPlanes(await request("GET", "/mantenimientos")); })}>{p.activo ? "Pausar" : "Activar"}</button></li>)}</ul></section>
    </>}

    {tab === "asambleas" && <>
      <p className="nota">Consultas comunitarias con registro de participación. La validez jurídica de las votaciones requiere revisión profesional.</p>
      {esAdmin && <section className="gestion-card"><h3>Preparar asamblea</h3><form className="gestion-form" onSubmit={enviar("/asambleas", (d) => ({ titulo: d.titulo, agenda: d.agenda, fecha: d.fecha, opciones: d.opciones.split("\n") }))}>
        <label>Título de asamblea<input name="titulo" minLength={3} maxLength={160} required /></label>
        <label>Agenda<textarea name="agenda" minLength={3} maxLength={10000} required /></label>
        <label>Fecha de asamblea<input name="fecha" type="datetime-local" required /></label>
        <label>Opciones de votación (una por línea)<textarea name="opciones" defaultValue={"A favor\nEn contra\nAbstención"} required /></label>
        <button className="btn" disabled={busy}>Crear borrador de asamblea</button></form></section>}
      {datos?.length === 0 && <p className="vacio">No hay asambleas disponibles.</p>}
      <ul className="items">{datos?.map((a) => <li key={a.id}><button className="mini" onClick={() => abrir(a.id)}>{a.titulo}</button> · {fh(a.fecha)} · {a.estado}</li>)}</ul>
      {detalle && <section className="gestion-card"><h3>{detalle.titulo}</h3><p>{detalle.agenda}</p><p>{detalle.participantes} representantes · {detalle.asistentes} asistentes</p>
        {esAdmin && detalle.estado === "borrador" && <><form className="fila-form" onSubmit={enviar(`/asambleas/${detalle.id}/participantes`, (d) => ({ residente_id: Number(d.residente_id) }), () => abrir(detalle.id))}>
          <label>Representante autorizado<select name="residente_id" required><option value="">Elegir representante</option>{personas.filter((r) => r.activo && r.rol !== "conserje").map((r) => <option key={r.id} value={r.id}>{r.nombre} · {r.unidad}</option>)}</select></label>
          <button className="btn" disabled={busy}>Agregar al padrón</button></form>
          <button className="btn" disabled={busy || !detalle.participantes} onClick={() => accion(async () => { await request("POST", `/asambleas/${detalle.id}/abrir`); await abrir(detalle.id); }, "Votación abierta. El padrón quedó fijado.")}>Abrir votación y fijar padrón</button></>}
        {detalle.estado === "abierta" && detalle.en_padron && !detalle.presente && <button className="btn" disabled={busy} onClick={() => accion(async () => { await request("POST", `/asambleas/${detalle.id}/asistencia`); await abrir(detalle.id); })}>Confirmar mi asistencia</button>}
        {detalle.puede_votar && <form className="gestion-form" onSubmit={enviar(`/asambleas/${detalle.id}/votos`, (d) => ({ opcion: Number(d.opcion) }), () => abrir(detalle.id))}>
          <fieldset><legend>Seleccione su voto. Al confirmar no podrá modificarlo.</legend>{detalle.opciones.map((o, i) => <label className="gestion-checkbox" key={i}><input type="radio" name="opcion" value={i} required />{o}</label>)}</fieldset>
          <button className="btn" disabled={busy}>Confirmar voto</button></form>}
        {detalle.mi_recibo && <p className="gestion-recibo">Recibo de su voto: <code>{detalle.mi_recibo}</code></p>}
        {esAdmin && detalle.estado === "abierta" && <form className="gestion-form" onSubmit={enviar(`/asambleas/${detalle.id}/cerrar`, undefined, () => abrir(detalle.id))}>
          <label>Acta y acuerdos<textarea name="acta" minLength={3} maxLength={20000} required /></label><button className="btn" disabled={busy}>Cerrar votación y guardar acta</button></form>}
        {detalle.resultados && <><h4>Resultados</h4><table className="tabla"><thead><tr><th>Opción</th><th>Votos</th><th>Coeficiente</th></tr></thead><tbody>{detalle.resultados.map((r, i) => <tr key={i}><td>{r.opcion}</td><td>{r.votos}</td><td>{r.coeficiente}</td></tr>)}</tbody></table><h4>Acta</h4><p className="gestion-texto">{detalle.acta}</p></>}
      </section>}
    </>}

    {tab === "documentos" && <>
      {esAdmin && <section className="gestion-card"><h3>Subir documento</h3><form className="gestion-form" onSubmit={async (e) => {
        e.preventDefault(); const f = e.currentTarget; const r = await accion(() => api.subirDocumento(new FormData(f)), "Documento recibido para procesar."); if (r) f.reset();
      }}><label>Título del documento<input name="titulo" minLength={3} maxLength={160} required /></label>
        <label>Archivo<input type="file" name="file" accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg" required /></label>
        <label>Categoría<select name="categoria"><option value="general">General</option><option value="reglamento">Reglamento</option><option value="contrato">Contrato</option><option value="factura">Factura</option><option value="acta">Acta</option></select></label>
        <label>Vencimiento del documento<input type="date" name="vence" /></label>
        <label className="gestion-checkbox"><input type="checkbox" name="publico_comunidad" value="true" />Disponible para residentes</label>
        <button className="btn" disabled={busy}>Subir documento</button></form></section>}
      {datos?.length === 0 && <p className="vacio">No hay documentos disponibles.</p>}
      <ul className="items">{datos?.map((d) => <li key={d.id}><label className="gestion-checkbox"><input type="checkbox" checked={fuentes.includes(d.id)} onChange={(e) => setFuentes(e.target.checked ? [...fuentes, d.id] : fuentes.filter((id) => id !== d.id))} />{d.titulo}</label>
        <span className="etq">{d.categoria}</span>
        <button className="mini" disabled={busy} onClick={() => accion(() => api.descargar(`/documentos/${d.id}/descargar`, d.titulo), "Documento descargado.")}>Descargar</button>
        <button className="mini" disabled={busy} onClick={() => accion(async () => { const r = await request("GET", `/documentos/${d.id}/estado`); setRespuesta({ estado: r }); }, "Estado actualizado.")}>Ver procesamiento</button>
        {esAdmin && <details><summary>Subir nueva versión</summary><form onSubmit={async (e) => { e.preventDefault(); const f = e.currentTarget; const r = await accion(() => api.subirDocumento(new FormData(f), d.id), "Nueva versión recibida."); if (r) f.reset(); }}>
          <label>Nueva versión de {d.titulo}<input type="file" name="file" accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg" required /></label><button className="btn" disabled={busy}>Guardar versión</button></form></details>}
      </li>)}</ul>
      <form className="gestion-form" onSubmit={async (e) => { e.preventDefault(); const d = datosForm(e); await accion(async () => setRespuesta(await request("POST", "/documentos/preguntar", { pregunta: d.pregunta, documentos: fuentes })), "Consulta completada."); }}>
        <label>Pregunta sobre los documentos seleccionados<textarea name="pregunta" minLength={3} maxLength={500} required /></label><button className="btn" disabled={busy || fuentes.length === 0 || fuentes.length > 25}>Consultar documentos</button>
      </form>
      {respuesta?.respuesta && <article className="gestion-card"><p>{respuesta.respuesta}</p>{respuesta.fuentes.map((f, i) => <blockquote key={i}><strong>{f.titulo} · página {f.pagina}</strong><p>{f.fragmento}</p></blockquote>)}</article>}
      {respuesta?.estado && <pre className="gestion-texto">{JSON.stringify(respuesta.estado, null, 2)}</pre>}
    </>}

    {tab === "notificaciones" && <>
      {datos?.length === 0 && <p className="vacio">No tiene notificaciones.</p>}
      <ul className="items">{datos?.map((n) => <li key={n.id}><b>{n.titulo}</b><p>{n.texto}</p><small>{fh(n.creado)}</small>
        {!n.leido ? <button className="mini" disabled={busy} onClick={() => accion(() => request("POST", `/notificaciones/${n.id}/leer`), "Notificación marcada como leída.")}>Marcar como leída</button> : <span className="etq">Leída</span>}</li>)}</ul>
    </>}

    {tab === "automatizaciones" && datos && esAdmin && <section className="gestion-card"><h3>Reglas de seguimiento</h3>
      <p>Crean incidencias programadas y avisos dentro de la aplicación. Los pagos y aperturas requieren una acción autorizada.</p>
      <form className="gestion-form" key={JSON.stringify(datos)} onSubmit={async (e) => {
        e.preventDefault(); const d = datosForm(e); await accion(() => request("PUT", "/automatizaciones", { activa: d.activa === "on", recordatorios_pago: d.recordatorios_pago === "on", contratos_dias: Number(d.contratos_dias), max_notificaciones: Number(d.max_notificaciones) }));
      }}><label className="gestion-checkbox"><input name="activa" type="checkbox" defaultChecked={datos.activa} />Automatizaciones activas</label>
        <label className="gestion-checkbox"><input name="recordatorios_pago" type="checkbox" defaultChecked={datos.recordatorios_pago} />Recordar deudas vencidas</label>
        <label>Avisar vencimientos con anticipación (días)<input name="contratos_dias" type="number" min="0" max="365" defaultValue={datos.contratos_dias} required /></label>
        <label>Máximo de avisos por ejecución<input name="max_notificaciones" type="number" min="1" max="1000" defaultValue={datos.max_notificaciones} required /></label>
        <button className="btn" disabled={busy}>Guardar automatizaciones</button></form>
      <button className="btn sec" disabled={busy} onClick={() => accion(() => request("POST", "/automatizaciones/ejecutar"), "Reglas revisadas; consulte las incidencias y notificaciones.")}>Ejecutar revisión ahora</button>
    </section>}
  </section>;
}
