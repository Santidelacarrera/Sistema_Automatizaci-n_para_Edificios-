"use client";
import { useCallback, useEffect, useState } from "react";
import { apiHasBackend, client, demoSession, listarEdificios, login, session } from "../lib/api";
import Administracion from "./components/Administracion";
import Edificios from "./components/Edificios";
import Cobranza from "./components/Cobranza";
import Drawer from "./components/Drawer";
import Fachada from "./components/Fachada";
import Porton from "./components/Porton";
import Visitas from "./components/Visitas";

const VISTAS = [["fachada", "Fachada"], ["porton", "Portón"], ["visitas", "Visitas"], ["cobranza", "Cobranza"], ["admin", "Administración"]];
const PUEDE_ADMIN = (sess) => sess.demo || sess.rol === "admin" || sess.rol === "superadmin";
const ES_SUPERADMIN = (sess) => !sess.demo && sess.rol === "superadmin";

function Login({ onOk }) {
  const [f, setF] = useState({ edificio_id: "", email: "", password: "" });
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault(); setBusy(true); setErr("");
    try { onOk(await login(f.edificio_id.trim(), f.email.trim(), f.password)); }
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
          <button className="btn" disabled={busy}>Entrar</button>
        </>)}
        {err && <p role="alert" className="aviso err">{err}</p>}
        <button type="button" className="btn sec" onClick={() => onOk(demoSession())}>Ver con datos de ejemplo</button>
      </form>
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

  const cargar = useCallback(async () => {
    try {
      const [d, a, v, c] = await Promise.all([api.panel(), api.accesos(), api.visitas(), api.cobranza()]);
      setData(d); setAccesos(a); setVisitas(v); setCob(c); setErr("");
    } catch (e) {
      if (e.status === 401) onSalir(); else setErr(e.message === "Failed to fetch" ? "Sin conexión con el servidor. Reintentando…" : e.message);
    }
  }, [sess.token, edificioId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setData(null); setSel(null); cargar(); const t = setInterval(cargar, 10000); return () => clearInterval(t); }, [cargar]);

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
        <div className="marca"><b>Fachada</b><span>{data.edificio.nombre}{sess.demo ? " · ejemplo" : ""}</span></div>
        {ES_SUPERADMIN(sesionInicial) && (
          <label className="selector-edificio">Edificio
            <select value={edificioId} onChange={(e) => abrirEdificio(e.target.value)}>
              {(edificios.length ? edificios : [{ id: edificioId, nombre: data.edificio.nombre }]).map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
            </select>
          </label>)}
        <nav aria-label="Secciones">
          {(ES_SUPERADMIN(sesionInicial) ? [["edificios", "Edificios"], ...VISTAS] : VISTAS).filter(([k]) => k !== "admin" || PUEDE_ADMIN(sess)).map(([k, t]) => (
            <button key={k} className={vista === k ? "tab on" : "tab"} aria-current={vista === k ? "page" : undefined} onClick={() => setVista(k)}>
              {t}{k === "cobranza" && cob.morosos.length > 0 ? <sup>{cob.morosos.length}</sup> : null}
            </button>))}
        </nav>
        <button className="salir" onClick={onSalir}>Salir</button>
      </header>
      {err && <p role="alert" className="banda">{err}</p>}
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
          {u && <Drawer key={u.id} u={u} api={api} onClose={() => setSel(null)} onChange={cargar} esAdmin={PUEDE_ADMIN(sess)} unidades={data.unidades} />}
        </>)}
        {vista === "porton" && <Porton accesos={accesos} data={data} />}
        {vista === "visitas" && <Visitas visitas={visitas} data={data} />}
        {vista === "cobranza" && <Cobranza cob={cob} api={api} onChange={cargar} />}
        {vista === "admin" && PUEDE_ADMIN(sess) && <Administracion key={edificioId} api={api} data={data} />}
        {vista === "edificios" && ES_SUPERADMIN(sesionInicial) && <Edificios lista={edificios} activo={edificioId} onAbrir={abrirEdificio} error={errEdificios} />}
      </main>
    </div>
  );
}

export default function Page() {
  const [sess, setSess] = useState(undefined);
  useEffect(() => { setSess(session.get()); }, []);
  const entrar = (s) => { session.set(s); setSess(s); };
  const salir = () => { session.clear(); setSess(null); };
  if (sess === undefined) return null;
  return sess ? <Panel sess={sess} onSalir={salir} /> : <Login onOk={entrar} />;
}
