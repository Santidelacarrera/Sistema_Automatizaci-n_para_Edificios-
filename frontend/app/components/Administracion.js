import { useEffect, useState } from "react";
import { erroresRegla, erroresResidente, mensajeError } from "../../lib/validar";

import AjustesAcceso from "./AjustesAcceso";
import PruebaAlcance from "./PruebaAlcance";

const SECCIONES = [["residentes", "Residentes"], ["tags", "Tags RFID"], ["reglas", "Reglas"], ["acceso", "Acceso"], ["alcance", "Prueba de alcance"]];
const ROLES = { residente: "Residente", admin: "Administrador", conserje: "Conserje" };
const TIPO_REGLA = {
  horario: "Horario permitido",
  max_por_mes: "Máximo por mes",
  bloquear_morosos: "Bloqueo a morosos",
  anticipacion: "Anticipación",
};
const VACIO_RESIDENTE = { nombre: "", rut: "", email: "", telefono: "", unidad_id: "", rol: "residente", activo: true, password: "" };

// Mensaje de estado común a las tres secciones.
function Aviso({ msg }) {
  if (!msg) return null;
  return <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>;
}

// Campo con su error debajo (el error también va en aria-describedby para lectores de pantalla).
function Campo({ id, label, error, children, ayuda }) {
  return (
    <div className="campo">
      <label htmlFor={id}>{label}</label>
      {children}
      {ayuda && !error && <span className="ayuda" id={`${id}-ayuda`}>{ayuda}</span>}
      {error && <span className="error-campo" id={`${id}-error`}>{error}</span>}
    </div>
  );
}

function Residentes({ api, data }) {
  const [lista, setLista] = useState([]);
  const [form, setForm] = useState(VACIO_RESIDENTE);
  const [editando, setEditando] = useState(null); // id del residente en edición
  const [errores, setErrores] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  const cargar = async () => setLista(await api.residentes());
  useEffect(() => { cargar().catch((e) => setMsg({ ok: false, t: mensajeError(e.detail ?? e.message) })); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const editar = (r) => {
    setEditando(r.id); setErrores({}); setMsg(null);
    setForm({ nombre: r.nombre, rut: r.rut, email: r.email, telefono: r.telefono, unidad_id: String(r.unidad_id), rol: r.rol, activo: r.activo, password: "" });
  };
  const limpiar = () => { setEditando(null); setForm(VACIO_RESIDENTE); setErrores({}); };
  const nuevo = () => { limpiar(); setMsg(null); };
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.value });

  const guardar = async (e) => {
    e.preventDefault();
    const err = erroresResidente(form);
    if (form.password && form.password.length < 8) err.password = "La contraseña debe tener al menos 8 caracteres.";
    setErrores(err);
    if (Object.keys(err).length) { setMsg({ ok: false, t: "Revisa los campos marcados." }); return; }
    const cuerpo = { ...form, unidad_id: Number(form.unidad_id) };
    if (!cuerpo.password) delete cuerpo.password;
    if (!editando) delete cuerpo.activo;
    setBusy(true);
    try {
      if (editando) await api.editarResidente(editando, cuerpo);
      else await api.crearResidente(cuerpo);
      setMsg({ ok: true, t: editando ? "Residente actualizado." : "Residente creado. Ya puede entrar con su correo y contraseña." });
      limpiar(); await cargar();  // no se borra el mensaje de éxito
    } catch (x) {
      setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) });
    }
    setBusy(false);
  };

  return (
    <div className="admin-seccion">
      <table className="tabla">
        <thead><tr><th>Nombre</th><th>RUT</th><th>Depto</th><th>Rol</th><th>Estado</th><th><span className="sr">Acción</span></th></tr></thead>
        <tbody>{lista.map((r) => (
          <tr key={r.id} className={r.activo ? "" : "inactivo"}>
            <td>{r.nombre}</td><td>{r.rut}</td><td className="n">{r.unidad}</td>
            <td>{ROLES[r.rol] || r.rol}</td><td>{r.activo ? "Activo" : "Dado de baja"}</td>
            <td><button className="mini" onClick={() => editar(r)} aria-label={`Editar a ${r.nombre}`}>Editar</button></td>
          </tr>))}</tbody>
      </table>

      <form className="form-admin" onSubmit={guardar} noValidate aria-labelledby="form-residente">
        <h3 id="form-residente">{editando ? "Editar residente" : "Nuevo residente"}</h3>
        <div className="grilla-form">
          <Campo id="res-nombre" label="Nombre completo" error={errores.nombre}>
            <input id="res-nombre" value={form.nombre} onChange={set("nombre")} aria-invalid={!!errores.nombre} /></Campo>
          <Campo id="res-rut" label="RUT" error={errores.rut} ayuda="Con puntos y guion, ej. 12.345.678-5">
            <input id="res-rut" value={form.rut} onChange={set("rut")} aria-invalid={!!errores.rut} inputMode="text" /></Campo>
          <Campo id="res-unidad" label="Departamento" error={errores.unidad_id}>
            <select id="res-unidad" value={form.unidad_id} onChange={set("unidad_id")} aria-invalid={!!errores.unidad_id}>
              <option value="">Elige…</option>
              {data.unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}
            </select></Campo>
          <Campo id="res-email" label="Correo" error={errores.email}>
            <input id="res-email" type="email" value={form.email} onChange={set("email")} aria-invalid={!!errores.email} /></Campo>
          <Campo id="res-telefono" label="Teléfono WhatsApp" error={errores.telefono} ayuda="Celular de 9 dígitos; se completa con +56">
            <input id="res-telefono" type="tel" value={form.telefono} onChange={set("telefono")} aria-invalid={!!errores.telefono} /></Campo>
          <Campo id="res-rol" label="Rol">
            <select id="res-rol" value={form.rol} onChange={set("rol")}>
              {Object.entries(ROLES).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select></Campo>
          <Campo id="res-password" label={editando ? "Nueva contraseña (opcional)" : "Contraseña (opcional)"} error={errores.password}
            ayuda="Sin contraseña no podrá entrar a la app todavía.">
            <input id="res-password" type="password" value={form.password} onChange={set("password")} autoComplete="new-password" aria-invalid={!!errores.password} /></Campo>
          {editando && (
            <label className="chk"><input type="checkbox" checked={form.activo} onChange={set("activo")} />Activo (desmarcar para dar de baja)</label>
          )}
        </div>
        <div className="acciones">
          <button className="btn" disabled={busy}>{editando ? "Guardar cambios" : "Crear residente"}</button>
          {editando && <button type="button" className="btn sec" onClick={nuevo}>Cancelar edición</button>}
        </div>
        <Aviso msg={msg} />
      </form>
    </div>
  );
}

function Tags({ api, data }) {
  const [lista, setLista] = useState([]);
  const [form, setForm] = useState({ unidad_id: "", uid: "", tipo: "vehicular", residente_id: "" });
  const [errores, setErrores] = useState({});
  const [msg, setMsg] = useState(null);
  const [residentes, setResidentes] = useState([]);

  const cargar = async () => setLista(await api.tags());
  useEffect(() => { cargar(); api.residentes().then(setResidentes).catch(() => {}); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const delDepto = residentes.filter((r) => String(r.unidad_id) === form.unidad_id && r.activo);
  const alta = async (e) => {
    e.preventDefault();
    const err = {};
    if (!form.unidad_id) err.unidad_id = "Elige el departamento.";
    if (!/^[0-9A-Fa-f]{8,20}$/.test(form.uid.trim())) err.uid = "El UID tiene entre 8 y 20 caracteres hexadecimales (0-9, A-F). Búscalo en la etiqueta del sticker o en el lector.";
    setErrores(err);
    if (Object.keys(err).length) { setMsg({ ok: false, t: "Revisa los campos marcados." }); return; }
    try {
      await api.crearTag({ unidad_id: Number(form.unidad_id), uid: form.uid.trim(), tipo: form.tipo, residente_id: form.residente_id ? Number(form.residente_id) : null });
      setMsg({ ok: true, t: "Tag registrado." });
      setForm({ ...form, uid: "", residente_id: "" }); await cargar();
    } catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
  };
  const cambiar = async (t, cambios, texto) => {
    try { await api.editarTag(t.id, cambios); setMsg({ ok: true, t: texto }); await cargar(); }
    catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
  };

  return (
    <div className="admin-seccion">
      <table className="tabla">
        <thead><tr><th>UID</th><th>Tipo</th><th>Depto</th><th>Residente</th><th>Estado</th><th><span className="sr">Acciones</span></th></tr></thead>
        <tbody>{lista.map((t) => (
          <tr key={t.id} className={t.activo ? "" : "inactivo"}>
            <td><code>{t.uid}</code></td><td>{t.tipo === "vehicular" ? "Vehicular" : "Peatonal"}</td>
            <td className="n">{t.unidad}</td><td>{t.residente || <span className="sin-pat">Sin asignar</span>}</td>
            <td>{t.activo ? "Activo" : "Desactivado"}</td>
            <td className="acc">
              <button className="mini" onClick={() => cambiar(t, { activo: !t.activo }, t.activo ? "Tag desactivado: ya no abre el portón." : "Tag reactivado.")}>
                {t.activo ? "Desactivar" : "Reactivar"}</button>
              {t.residente_id && <button className="mini" onClick={() => cambiar(t, { residente_id: null }, "Tag desvinculado del residente.")}>Desvincular</button>}
            </td>
          </tr>))}</tbody>
      </table>

      <form className="form-admin" onSubmit={alta} noValidate aria-labelledby="form-tag">
        <h3 id="form-tag">Registrar tag</h3>
        <div className="grilla-form">
          <Campo id="tag-unidad" label="Departamento" error={errores.unidad_id}>
            <select id="tag-unidad" value={form.unidad_id} onChange={(e) => setForm({ ...form, unidad_id: e.target.value, residente_id: "" })} aria-invalid={!!errores.unidad_id}>
              <option value="">Elige…</option>
              {data.unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}
            </select></Campo>
          <Campo id="tag-uid" label="UID del tag" error={errores.uid} ayuda="Hexadecimal, ej. 04A1B2C3">
            <input id="tag-uid" value={form.uid} onChange={(e) => setForm({ ...form, uid: e.target.value.toUpperCase() })} aria-invalid={!!errores.uid} /></Campo>
          <Campo id="tag-tipo" label="Tipo">
            <select id="tag-tipo" value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
              <option value="vehicular">Vehicular (portón, 10 a 15 m)</option>
              <option value="peatonal">Peatonal (llavero)</option>
            </select></Campo>
          <Campo id="tag-residente" label="Residente (opcional)">
            <select id="tag-residente" value={form.residente_id} onChange={(e) => setForm({ ...form, residente_id: e.target.value })} disabled={!form.unidad_id}>
              <option value="">Sin asignar</option>
              {delDepto.map((r) => <option key={r.id} value={r.id}>{r.nombre}</option>)}
            </select></Campo>
        </div>
        <div className="acciones"><button className="btn">Registrar tag</button></div>
        <Aviso msg={msg} />
      </form>
    </div>
  );
}

function Reglas({ api }) {
  const [lista, setLista] = useState([]);
  const [espacios, setEspacios] = useState([]);
  const [form, setForm] = useState({ accion: "", tipo: "horario", desde: "10:00", hasta: "22:00", max: "2", deuda_max: "0", min_horas: "", max_dias: "" });
  const [errores, setErrores] = useState({});
  const [msg, setMsg] = useState(null);

  const cargar = async () => setLista(await api.reglas());
  useEffect(() => {
    cargar();
    api.espacios().then((e) => { setEspacios(e); if (e[0]) setForm((f) => ({ ...f, accion: e[0].accion })); }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const params = () => {
    if (form.tipo === "horario") return { desde: form.desde, hasta: form.hasta };
    if (form.tipo === "max_por_mes") return { max: Number(form.max) };
    if (form.tipo === "bloquear_morosos") return { deuda_max: Number(form.deuda_max) };
    const p = {};
    if (form.min_horas !== "") p.min_horas = Number(form.min_horas);
    if (form.max_dias !== "") p.max_dias = Number(form.max_dias);
    return p;
  };
  const alta = async (e) => {
    e.preventDefault();
    const err = erroresRegla({ tipo: form.tipo, params: params() });
    setErrores(err);
    if (!form.accion) err.accion = "Elige el espacio común.";
    if (Object.keys(err).length) { setMsg({ ok: false, t: "Revisa los campos marcados." }); return; }
    try {
      await api.crearRegla({ accion: form.accion, tipo: form.tipo, params: params() });
      setMsg({ ok: true, t: "Regla creada." }); await cargar();
    } catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
  };
  const activar = async (r) => {
    try { await api.editarRegla(r.id, { activa: !r.activa }); setMsg({ ok: true, t: r.activa ? "Regla pausada." : "Regla activada." }); await cargar(); }
    catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
  };
  const nombreEspacio = (accion) => espacios.find((e) => e.accion === accion)?.nombre ?? accion;

  return (
    <div className="admin-seccion">
      <table className="tabla">
        <thead><tr><th>Espacio</th><th>Regla</th><th>Detalle</th><th>Estado</th><th><span className="sr">Acción</span></th></tr></thead>
        <tbody>{lista.map((r) => (
          <tr key={r.id} className={r.activa ? "" : "inactivo"}>
            <td>{nombreEspacio(r.accion)}</td><td>{TIPO_REGLA[r.tipo] || r.tipo}</td>
            <td><code>{JSON.stringify(r.params)}</code></td><td>{r.activa ? "Vigente" : "En pausa"}</td>
            <td><button className="mini" onClick={() => activar(r)}>{r.activa ? "Pausar" : "Activar"}</button></td>
          </tr>))}</tbody>
      </table>

      <form className="form-admin" onSubmit={alta} noValidate aria-labelledby="form-regla">
        <h3 id="form-regla">Nueva regla</h3>
        <div className="grilla-form">
          <Campo id="regla-espacio" label="Espacio común" error={errores.accion}>
            <select id="regla-espacio" value={form.accion} onChange={(e) => setForm({ ...form, accion: e.target.value })}>
              {espacios.map((e) => <option key={e.id} value={e.accion}>{e.nombre}</option>)}
            </select></Campo>
          <Campo id="regla-tipo" label="Tipo de regla">
            <select id="regla-tipo" value={form.tipo} onChange={(e) => setForm({ ...form, tipo: e.target.value })}>
              {Object.entries(TIPO_REGLA).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select></Campo>
          {form.tipo === "horario" && (<>
            <Campo id="regla-desde" label="Desde"><input id="regla-desde" type="time" value={form.desde} onChange={(e) => setForm({ ...form, desde: e.target.value })} /></Campo>
            <Campo id="regla-hasta" label="Hasta" error={errores.hasta}><input id="regla-hasta" type="time" value={form.hasta} onChange={(e) => setForm({ ...form, hasta: e.target.value })} aria-invalid={!!errores.hasta} /></Campo>
          </>)}
          {form.tipo === "max_por_mes" && (
            <Campo id="regla-max" label="Máximo de usos por mes" error={errores.max}><input id="regla-max" type="number" min="1" max="31" value={form.max} onChange={(e) => setForm({ ...form, max: e.target.value })} aria-invalid={!!errores.max} /></Campo>)}
          {form.tipo === "bloquear_morosos" && (
            <Campo id="regla-deuda" label="Deuda máxima permitida ($)" error={errores.deuda_max} ayuda="0 = sin ninguna deuda"><input id="regla-deuda" type="number" min="0" value={form.deuda_max} onChange={(e) => setForm({ ...form, deuda_max: e.target.value })} aria-invalid={!!errores.deuda_max} /></Campo>)}
          {form.tipo === "anticipacion" && (<>
            <Campo id="regla-min" label="Anticipación mínima (horas)" error={errores.min_horas}><input id="regla-min" type="number" min="0" value={form.min_horas} onChange={(e) => setForm({ ...form, min_horas: e.target.value })} aria-invalid={!!errores.min_horas} /></Campo>
            <Campo id="regla-max-dias" label="Anticipación máxima (días)" error={errores.max_dias}><input id="regla-max-dias" type="number" min="1" max="365" value={form.max_dias} onChange={(e) => setForm({ ...form, max_dias: e.target.value })} aria-invalid={!!errores.max_dias} /></Campo>
          </>)}
        </div>
        <div className="acciones"><button className="btn">Crear regla</button></div>
        <Aviso msg={msg} />
      </form>
    </div>
  );
}

export default function Administracion({ api, data }) {
  const [seccion, setSeccion] = useState("residentes");
  return (
    <div className="admin-vista">
      <header className="vista-cab">
        <h2>Administración</h2>
        <p>Residentes, tags RFID y reglas del edificio. Cada cambio queda registrado; los datos dados de baja se conservan.</p>
      </header>
      <nav className="subtabs" aria-label="Sección de administración">
        {SECCIONES.map(([k, t]) => (
          <button key={k} className={seccion === k ? "tab on" : "tab"} aria-current={seccion === k ? "true" : undefined} onClick={() => setSeccion(k)}>{t}</button>))}
      </nav>
      {seccion === "residentes" && <Residentes api={api} data={data} />}
      {seccion === "tags" && <Tags api={api} data={data} />}
      {seccion === "reglas" && <Reglas api={api} />}
      {seccion === "acceso" && <AjustesAcceso api={api} />}
      {seccion === "alcance" && <PruebaAlcance api={api} />}
    </div>
  );
}
