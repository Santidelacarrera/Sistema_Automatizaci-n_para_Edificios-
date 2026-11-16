"use client";
import { useState } from "react";
import { Estado, fh } from "./ui";

export default function Dispositivos({ api, lista, recargar }) {
  const [msg, setMsg] = useState(null);
  const [clave, setClave] = useState(null);
  const [seleccionado, setSeleccionado] = useState(null);
  const [historial, setHistorial] = useState([]);
  const [busy, setBusy] = useState(false);
  const ejecutar = async (fn) => {
    setBusy(true); setMsg(null);
    try { const r = await fn(); await recargar(); setMsg({ ok: true, t: "Operación registrada." }); return r; }
    catch (e) { setMsg({ ok: false, t: e.message }); return null; } finally { setBusy(false); }
  };
  return <>
    <p className="nota">Las aperturas de esta sección se simulan en laboratorio. El control físico con ESP32 conserva su protocolo de acceso existente.</p>
    <Estado msg={msg} />
    <section className="gestion-card"><h3>Registrar controlador</h3><form className="gestion-form" onSubmit={async (e) => {
      e.preventDefault(); const f = e.currentTarget; const b = Object.fromEntries(new FormData(f));
      const r = await ejecutar(() => api.operar("POST", "/dispositivos", { nombre: b.nombre, punto: b.punto, laboratorio: b.laboratorio === "on" }));
      if (r) { setClave(r); f.reset(); }
    }}><label>Nombre del controlador<input name="nombre" required minLength={2} maxLength={80} /></label>
      <label>Puerta o punto de acceso<input name="punto" required minLength={2} maxLength={40} /></label>
      <label className="gestion-checkbox"><input name="laboratorio" type="checkbox" defaultChecked />Dispositivo de laboratorio</label>
      <button className="btn" disabled={busy}>Registrar controlador</button></form>
      {clave && <div className="aviso"><p>Clave del dispositivo #{clave.id}. Guárdela ahora; no se vuelve a mostrar.</p><code className="gestion-recibo">{clave.clave}</code><button className="mini" onClick={() => setClave(null)}>Ocultar clave</button></div>}
    </section>
    <button className="btn sec" disabled={busy} onClick={() => ejecutar(recargar)}>Actualizar estado</button>
    {!lista?.length && <p className="vacio">No hay controladores registrados.</p>}
    <ul className="items">{lista?.map((d) => <li key={d.id}><b>{d.nombre}</b> · {d.punto} · {d.activo ? (d.conectado ? "Conectado" : "Sin comunicación reciente") : "Desactivado"}
      <p>{d.laboratorio ? "Laboratorio" : "Sólo telemetría"} · Firmware {d.firmware || "sin informar"} · Última señal: {fh(d.ultima_comunicacion)}{d.bateria != null && ` · Batería ${d.bateria}%`}</p>
      <button className="mini" disabled={busy} onClick={() => ejecutar(async () => { setSeleccionado(d); setHistorial(await api.operar("GET", `/dispositivos/${d.id}/comandos`)); })}>Gestionar {d.nombre}</button>
    </li>)}</ul>
    {seleccionado && <section className="gestion-card"><h3>{seleccionado.nombre}</h3>
      <button className="btn sec" disabled={busy} onClick={() => ejecutar(async () => { await api.operar("PATCH", `/dispositivos/${seleccionado.id}`, { activo: !seleccionado.activo }); setSeleccionado(null); })}>{seleccionado.activo ? "Desactivar dispositivo" : "Activar dispositivo"}</button>
      <details><summary>Rotar la clave del controlador</summary><p>La clave anterior dejará de funcionar y se cancelarán los comandos pendientes.</p>
        <button className="btn peligro" disabled={busy} onClick={() => ejecutar(async () => { setClave(await api.operar("POST", `/dispositivos/${seleccionado.id}/rotar`)); })}>Confirmar rotación</button></details>
      {seleccionado.laboratorio && seleccionado.activo && <form className="gestion-form" onSubmit={async (e) => {
        e.preventDefault(); const f = e.currentTarget; const b = Object.fromEntries(new FormData(f));
        const r = await ejecutar(() => api.operar("POST", `/dispositivos/${seleccionado.id}/abrir`, { ...b, idempotencia: crypto.randomUUID() }));
        if (r) { f.reset(); setHistorial(await api.operar("GET", `/dispositivos/${seleccionado.id}/comandos`)); }
      }}><label>Motivo del ensayo<input name="motivo" required minLength={10} maxLength={200} /></label>
        <label>Contraseña para autorizar<input name="password" type="password" required autoComplete="current-password" /></label>
        <button className="btn" disabled={busy}>Autorizar apertura simulada</button></form>}
      <h4>Historial de comandos</h4><button className="mini" disabled={busy} onClick={() => ejecutar(async () => setHistorial(await api.operar("GET", `/dispositivos/${seleccionado.id}/comandos`)))}>Actualizar confirmaciones</button>
      <ul className="items">{historial.map((c) => <li key={c.id}>#{c.id} · {c.estado} · {c.motivo} · {fh(c.creado)}{c.confirmado && ` · Confirmado ${fh(c.confirmado)}`}</li>)}</ul>
    </section>}
  </>;
}
