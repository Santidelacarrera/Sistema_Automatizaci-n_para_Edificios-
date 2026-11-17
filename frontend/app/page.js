"use client";
import { useCallback, useEffect, useState } from "react";
import { apiHasBackend, cerrarSesion, client, confirmarMfa, crearEdificio, demoSession, editarEdificio, listarEdificios, login, prepararMfa, session } from "../lib/api";
import Operaciones from "./components/Operaciones";
import Comercial from "./components/Comercial";
import Administracion from "./components/Administracion";
import Edificios from "./components/Edificios";
import Cobranza from "./components/Cobranza";
import Comunidad from "./components/Comunidad";
import MiDepto from "./components/MiDepto";
import Drawer from "./components/Drawer";
import Fachada from "./components/Fachada";
import Finanzas from "./components/Finanzas";
import Porton from "./components/Porton";
import Reservas from "./components/Reservas";
import Visitas from "./components/Visitas";
import PortalPropietario from "./components/PortalPropietario";

const VISTAS = [["fachada", "Fachada"], ["propietario", "Mi Depto"], ["porton", "Portón"], ["visitas", "Visitas"], ["reservas", "Reservas"], ["cobranza", "Cobranza"], ["comunidad", "Conserjería"], ["finanzas", "Finanzas"], ["admin", "Administración"]];
const SOLO_ADMIN = ["admin", "finanzas", "reservas", "cobranza", "propietario"];
const PUEDE_ADMIN = (sess) => sess.demo || sess.rol === "admin" || sess.rol === "superadmin";
const ES_SUPERADMIN = (sess) => !sess.demo && sess.rol === "superadmin";

function Login({ onOk }) {
  const [f, setF] = useState({ edificio_id: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [codigo, setCodigo] = useState("");
  const [setup, setSetup] = useState(null);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (setup) { onOk(await confirmarMfa(setup.token, codigo)); }
      else {
        const s = await login(f.edificio_id.trim(), f.email.trim(), f.password, codigo);
        if (s.mfa_setup_required) {
          const provision = await prepararMfa(s.setup_token, f.password);
          setSetup({ ...provision, token: s.setup_token }); setCodigo("");
        } else onOk(s);
      }
    }
    catch (x) { setErr(x.message === "Failed to fetch" ? "No hay conexión con el servidor." : x.message); }
    setBusy(false);
  };
  return (
    <main className="entrada">
      <div className="entrada-fachada" aria-hidden="true">
        {Array.from({ length: 28 }, (_, i) => <span key={i} className={[3, 9, 10, 17, 22].includes(i) ? "e-on" : [5, 14, 25].includes(i) ? "e-off" : ""} />)}
      </div>
      <form className="entrada-form" onSubmit={submit}>
        <h1>Fachada</h1>
        <p>Administre accesos, patentes, visitas y cobranza de su edificio.</p>
        {apiHasBackend() && (<>
          <label>Edificio<input value={f.edificio_id} onChange={(e) => setF({ ...f, edificio_id: e.target.value })} placeholder="edificio_a" required /></label>
          <label>Correo<input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} required autoComplete="username" /></label>
          <label>Contraseña<input type="password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required autoComplete="current-password" /></label>
          {setup && <div className="aviso"><p>Agregue esta clave a su aplicación autenticadora y confirme el código de seis dígitos para proteger la cuenta.</p><code className="gestion-recibo">{setup.secreto}</code></div>}
          <label>Código de autenticador{!setup && " (si está activo)"}<input value={codigo} onChange={(e) => setCodigo(e.target.value)} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} required={Boolean(setup)} /></label>
          <button className="btn" disabled={busy}>Entrar</button>
        </>)}
        {err && <p role="alert" className="aviso err">{err}</p>}
        <button type="button" className="btn sec" onClick={() => onOk(demoSession())}>Ver con datos de ejemplo</button>
      </form>
      <section className="landing-publica" aria-label="Información de la plataforma">
        <h2>Plataforma integral de administración y automatización de edificios</h2>
        <ul>
          <li><strong>Finanzas y gastos comunes:</strong> prorrateo automático, conciliación bancaria, multas, fondo de reserva y reportes PDF.</li>
          <li><strong>Portería y control de acceso:</strong> pases QR, visitas recurrentes, encomiendas, proveedores/delivery y laboratorio IoT.</li>
          <li><strong>Comunidad y gobernanza:</strong> reservas con garantías, asambleas con actas PDF, encuestas y analítica asistida.</li>
        </ul>
      </section>
    </main>
  );
}

function Panel({ sess: sesionInicial, onSalir }) {
  const [edificioId, setEdificioId] = useState(sesionInicial.edificio_id);
  const [edificios, setEdificios] = useState([]);
  const [errEdificios, setErrEdificios] = useState("");
  const sess = { ...sesionInicial, edificio_id: edificioId };
  const api = client(sess);
  const [vista, setVista] = useState("fachada");
  const [data, setData] = useState(null);
  const [accesos, setAccesos] = useState([]);
  const [visitas, setVisitas] = useState([]);
  const [cob, setCob] = useState({ morosos: [], total: 0 });
  const [sel, setSel] = useState(null);
  const [filtro, setFiltro] = useState(null);
  const [err, setErr] = useState("");
  const [tema, setTema] = useState("claro");
  const [sidebarAbierto, setSidebarAbierto] = useState(true);
  const [busqueda, setBusqueda] = useState("");
  const [resultadosBusq, setResultadosBusq] = useState(null);

  useEffect(() => {
    const saved = typeof window !== "undefined" ? window.localStorage.getItem("fachada_tema") : null;
    if (saved === "oscuro") setTema("oscuro");
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-theme", tema === "oscuro" ? "dark" : "light");
      window.localStorage.setItem("fachada_tema", tema);
    }
  }, [tema]);

  useEffect(() => {
    const q = busqueda.trim();
    if (q.length < 2) { setResultadosBusq(null); return; }
    if (sess.demo && data) {
      const t = q.toLowerCase();
      setResultadosBusq({
        unidades: data.unidades.filter((x) => x.numero.toLowerCase().includes(t)).slice(0, 6),
        residentes: [], incidencias: [], documentos: [], proveedores: [],
      });
      return;
    }
    const timer = setTimeout(() => {
      api.operar("GET", `/buscar?q=${encodeURIComponent(q)}`).then(setResultadosBusq).catch(() => {});
    }, 250);
    return () => clearTimeout(timer);
  }, [busqueda, edificioId]); // eslint-disable-line react-hooks/exhaustive-deps

  const cargar = useCallback(async () => {
    try {
      const [d, a, v, c] = await Promise.all([api.panel(), api.accesos(), api.visitas(),
        PUEDE_ADMIN(sess) ? api.cobranza() : Promise.resolve({ morosos: [], total: 0 })]);
      setData(d); setAccesos(a); setVisitas(v); setCob(c); setErr("");
    } catch (e) {
      if (e.status === 401) onSalir(); else setErr(e.message === "Failed to fetch" ? "Sin conexión con el servidor. Reintentando…" : e.message);
    }
  }, [sess.token, edificioId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setData(null); setSel(null); cargar(); const t = setInterval(cargar, 10000); return () => clearInterval(t); }, [cargar]);

  // Al cambiar de sección se refresca al tiro: el portón y la cobranza no deben mostrar datos de hace 10 s.
  useEffect(() => { cargar(); }, [vista]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!ES_SUPERADMIN(sesionInicial)) return;
    listarEdificios(sesionInicial).then(setEdificios).catch((e) => setErrEdificios(e.message));
  }, [sesionInicial.token]); // eslint-disable-line react-hooks/exhaustive-deps

  const abrirEdificio = (id) => { setEdificioId(id); setVista("fachada"); };

  if (!data) return <main className="cargando">{err || "Abriendo el edificio…"}</main>;
  const u = data.unidades.find((x) => x.id === sel);
  const n = (p) => data.unidades.filter(p).length;
  const resumen = [["persiana", `${n((x) => x.vencida > 0)} con deuda vencida`], ["encendida", `${n((x) => x.visitas_activas > 0)} con visita`], ["vacia", `${n((x) => !x.residentes.length)} sin residentes`]];

  return (
    <div className="shell">
      <header className="cab">
        <div className="cab-izq">
          <button type="button" className="btn-icono" aria-label="Alternar barra lateral" onClick={() => setSidebarAbierto((v) => !v)}>☰</button>
          <div className="marca"><b>Fachada</b><span>{data.edificio.nombre}{sess.demo ? " · ejemplo" : ""}</span></div>
        </div>
        {ES_SUPERADMIN(sesionInicial) && (
          <label className="selector-edificio">Edificio
            <select value={edificioId} onChange={(e) => abrirEdificio(e.target.value)}>
              {(edificios.length ? edificios : [{ id: edificioId, nombre: data.edificio.nombre }]).map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
            </select>
          </label>)}
        <div className="busqueda-global">
          <input type="search" aria-label="Búsqueda global" placeholder="Buscar depto, residente, documento…"
            value={busqueda} onChange={(e) => setBusqueda(e.target.value)} />
          {resultadosBusq && (
            <div className="busqueda-resultados">
              {resultadosBusq.unidades?.map((uItem) => (
                <button key={`u-${uItem.id}`} type="button" onClick={() => { setSel(uItem.id); setVista("fachada"); setBusqueda(""); setResultadosBusq(null); }}>
                  Depto {uItem.numero}{uItem.torre ? ` · Torre ${uItem.torre}` : ""}
                </button>
              ))}
              {resultadosBusq.residentes?.map((rItem) => (
                <button key={`r-${rItem.id}`} type="button" onClick={() => { setSel(rItem.unidad_id); setVista("fachada"); setBusqueda(""); setResultadosBusq(null); }}>
                  Residente: {rItem.nombre}
                </button>
              ))}
              {resultadosBusq.incidencias?.map((iItem) => (
                <button key={`i-${iItem.id}`} type="button" onClick={() => { setVista("operaciones"); setBusqueda(""); setResultadosBusq(null); }}>
                  Incidencia: {iItem.titulo} ({iItem.estado})
                </button>
              ))}
              {resultadosBusq.documentos?.map((dItem) => (
                <button key={`d-${dItem.id}`} type="button" onClick={() => { setVista("operaciones"); setBusqueda(""); setResultadosBusq(null); }}>
                  Doc: {dItem.titulo}
                </button>
              ))}
              {(!resultadosBusq.unidades?.length && !resultadosBusq.residentes?.length && !resultadosBusq.incidencias?.length && !resultadosBusq.documentos?.length) && (
                <span className="busqueda-vacia">Sin coincidencias</span>
              )}
            </div>
          )}
        </div>
        <div className="cab-acciones">
          <button type="button" className="btn-tema" title="Cambiar tema claro u oscuro" onClick={() => setTema((t) => (t === "oscuro" ? "claro" : "oscuro"))}>
            {tema === "oscuro" ? "Modo claro" : "Modo oscuro"}
          </button>
          <button className="salir" onClick={onSalir}>Salir</button>
        </div>
      </header>
      {err && <p role="alert" className="banda">{err}</p>}
      <div className="cuerpo-layout">
        <nav aria-label="Secciones" className={sidebarAbierto ? "sidebar" : "sidebar colapsada"}>
          {[...(ES_SUPERADMIN(sesionInicial) ? [["edificios", "Edificios"], ["comercial", "Administración SaaS"], ...VISTAS] : VISTAS),
            ...(!sess.demo ? [["operaciones", "Gestión comunitaria"]] : [])].filter(([k]) => !SOLO_ADMIN.includes(k) || PUEDE_ADMIN(sess)).map(([k, t]) => (
            <button key={k} className={vista === k ? "tab on" : "tab"} aria-current={vista === k ? "page" : undefined} onClick={() => setVista(k)}>
              {t}{k === "cobranza" && cob.morosos.length > 0 ? <sup>{cob.morosos.length}</sup> : null}
            </button>))}
        </nav>
        <main className={`vista ${u && vista === "fachada" ? "con-drawer" : ""}`}>
        {vista === "fachada" && (<>
          <section className="centro">
            <div className="resumen">
              {resumen.map(([k, t]) => (
                <button key={k} className={`chip ${filtro === k ? "on" : ""}`} onClick={() => setFiltro(filtro === k ? null : k)}>
                  <i className={`ventana-mini ${k}`} />{t}</button>))}
            </div>
            <Fachada data={data} filtro={filtro} seleccionada={sel} onSelect={setSel} />
          </section>
          {u && <Drawer key={u.id} u={u} api={api} onClose={() => setSel(null)} onChange={cargar} esAdmin={PUEDE_ADMIN(sess)} unidades={data.unidades} onVerPortal={(id) => { setSel(id); setVista("propietario"); }} />}
        </>)}
        {vista === "propietario" && <PortalPropietario data={data} api={api} sess={sess} deptoInicial={sel} />}
        {vista === "porton" && <Porton accesos={accesos} data={data} />}
        {vista === "visitas" && <Visitas visitas={visitas} data={data} api={api} />}
        {vista === "cobranza" && <Cobranza cob={cob} api={api} onChange={cargar} />}
        {vista === "reservas" && PUEDE_ADMIN(sess) && <Reservas key={edificioId} api={api} data={data} onChange={cargar} />}
        {vista === "finanzas" && PUEDE_ADMIN(sess) && <Finanzas key={edificioId} api={api} data={data} onChange={cargar} />}
        {vista === "comunidad" && <Comunidad key={edificioId} api={api} data={data} esAdmin={PUEDE_ADMIN(sess)} onChange={cargar} />}
        {vista === "admin" && PUEDE_ADMIN(sess) && <Administracion key={edificioId} api={api} data={data} />}
        {vista === "operaciones" && !sess.demo && <Operaciones key={edificioId} api={api} esAdmin={PUEDE_ADMIN(sess)} />}
        {vista === "comercial" && ES_SUPERADMIN(sesionInicial) && <Comercial sess={sesionInicial} edificios={edificios} />}
        {vista === "edificios" && ES_SUPERADMIN(sesionInicial) && <Edificios lista={edificios} activo={edificioId} onAbrir={abrirEdificio} error={errEdificios}
          onCrear={async (body) => { await crearEdificio(sesionInicial, body); setEdificios(await listarEdificios(sesionInicial)); }}
          onEditar={async (id, body) => { await editarEdificio(sesionInicial, id, body); setEdificios(await listarEdificios(sesionInicial)); }} />}
      </main>
      </div>
    </div>
  );
}

export default function Page() {
  const [sess, setSess] = useState(undefined);
  useEffect(() => { setSess(session.get()); }, []);
  const entrar = (s) => { session.set(s); setSess(s); };
  const salir = async () => { try { await cerrarSesion(sess); } catch { /* Sesión local siempre se cierra; el servidor puede estar desconectado. */ } finally { session.clear(); setSess(null); } };
  if (sess === undefined) return null;
  if (sess && !sess.demo && sess.rol === "residente") return <MiDepto api={client(sess)} nombre={sess.nombre} onSalir={salir} />;
  return sess ? <Panel sess={sess} onSalir={salir} /> : <Login onOk={entrar} />;
}
