import { useEffect, useState } from "react";
import { mensajeError } from "../../lib/validar";

export const MODOS = [
  { valor: "sticker_o_patente", titulo: "Sticker o patente", texto: "Abre con cualquiera de las dos. Es lo más cómodo; si alguien copia el sticker, puede abrir sin el auto." },
  { valor: "sticker_y_patente", titulo: "Sticker y patente", texto: "Abre sólo si el sticker y la patente son del mismo vehículo y se leen dentro de la ventana. Más seguro frente a clonación; exige buena lectura de patente." },
  { valor: "solo_sticker", titulo: "Sólo sticker", texto: "Ignora la cámara. Si el sticker no se lee, no abre." },
  { valor: "solo_patente", titulo: "Sólo patente", texto: "Ignora el sticker. Depende por completo de la cámara y de la luz." },
];

function ClaveLectores({ api }) {
  const [confirmar, setConfirmar] = useState(false);
  const [clave, setClave] = useState(null);
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const rotar = async () => {
    setBusy(true); setMsg(null);
    try { setClave((await api.rotarClaveLectores()).device_key); setConfirmar(false); }
    catch (e) { setMsg(mensajeError(e.detail ?? e.message)); }
    setBusy(false);
  };
  return (
    <section className="clave-lectores" aria-labelledby="clave-titulo">
      <h3 id="clave-titulo">Clave de los lectores</h3>
      <p className="ayuda">Cada lector se identifica con una clave. Si se pierde un lector o sospecha de una filtración, genere una nueva: los lectores con la clave anterior dejan de abrir hasta que se les cargue la nueva.</p>
      {clave ? (
        <div role="status" className="aviso ok">
          <p>Nueva clave (se muestra una sola vez; cópiela ahora):</p>
          <p><code className="clave-visible">{clave}</code></p>
          <button type="button" className="btn sec" onClick={() => navigator.clipboard?.writeText(clave)}>Copiar</button>{" "}
          <button type="button" className="btn sec" onClick={() => setClave(null)}>Ya la guardé</button>
        </div>
      ) : confirmar ? (
        <div className="aviso err" role="alertdialog" aria-label="Confirmar cambio de clave">
          <p>Los lectores dejarán de abrir hasta que les cargue la clave nueva. ¿Continuar?</p>
          <button type="button" className="btn" disabled={busy} onClick={rotar}>Sí, generar clave nueva</button>{" "}
          <button type="button" className="btn sec" onClick={() => setConfirmar(false)}>Cancelar</button>
        </div>
      ) : (
        <button type="button" className="btn sec" onClick={() => setConfirmar(true)}>Generar clave nueva</button>
      )}
      {msg && <p role="status" className="aviso err">{msg}</p>}
    </section>
  );
}

export default function AjustesAcceso({ api }) {
  const [a, setA] = useState(null);
  const [errores, setErrores] = useState({});
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { api.ajustesAcceso().then(setA).catch((e) => setMsg({ ok: false, t: mensajeError(e.detail ?? e.message) })); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  if (!a) return <p className="vacio">Cargando ajustes…</p>;
  const set = (k) => (e) => setA({ ...a, [k]: e.target.type === "checkbox" ? e.target.checked : e.target.type === "number" ? Number(e.target.value) : e.target.value });

  const guardar = async (e) => {
    e.preventDefault();
    const err = {};
    if (!(a.ventana_coincidencia_s >= 1 && a.ventana_coincidencia_s <= 120)) err.ventana_coincidencia_s = "Entre 1 y 120 segundos.";
    if (!(a.antirrebote_s >= 0 && a.antirrebote_s <= 60)) err.antirrebote_s = "Entre 0 y 60 segundos (0 = sin antirrebote).";
    if (!(a.umbral_confianza_patente >= 0 && a.umbral_confianza_patente <= 1)) err.umbral_confianza_patente = "Entre 0 y 1 (por ejemplo 0,85).";
    setErrores(err);
    if (Object.keys(err).length) { setMsg({ ok: false, t: "Revisa los valores marcados." }); return; }
    setBusy(true); setMsg(null);
    try {
      setA(await api.guardarAjustes({
        modo_acceso: a.modo_acceso, ventana_coincidencia_s: a.ventana_coincidencia_s, antirrebote_s: a.antirrebote_s,
        anti_passback: a.anti_passback, umbral_confianza_patente: a.umbral_confianza_patente,
      }));
      setMsg({ ok: true, t: "Ajustes guardados. Rigen desde la próxima lectura." });
    } catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
    setBusy(false);
  };

  const modo = MODOS.find((m) => m.valor === a.modo_acceso);
  return (
    <>
    <form className="form-admin" onSubmit={guardar} noValidate aria-labelledby="ajustes-titulo">
      <h3 id="ajustes-titulo">Cómo abre el portón</h3>
      <fieldset className="modos">
        <legend>Modo de acceso vehicular</legend>
        {MODOS.map((m) => (
          <label key={m.valor} className={`modo ${a.modo_acceso === m.valor ? "on" : ""}`}>
            <input type="radio" name="modo" value={m.valor} checked={a.modo_acceso === m.valor} onChange={set("modo_acceso")} />
            <span><b>{m.titulo}</b><span className="ayuda">{m.texto}</span></span>
          </label>
        ))}
      </fieldset>
      <p className="nota" role="note">Modo elegido: <b>{modo?.titulo}</b>. {modo?.valor === "sticker_y_patente" ? "Recomendado donde el riesgo de clonación sea alto." : ""}</p>

      <div className="grilla-form">
        <div className="campo">
          <label htmlFor="aj-ventana">Ventana de coincidencia (segundos)</label>
          <input id="aj-ventana" type="number" min="1" max="120" value={a.ventana_coincidencia_s} onChange={set("ventana_coincidencia_s")} aria-invalid={!!errores.ventana_coincidencia_s} aria-describedby="aj-ventana-ayuda" />
          <span className="ayuda" id="aj-ventana-ayuda">Tiempo máximo entre el sticker y la patente en modo "sticker y patente". Por defecto 10 s.</span>
          {errores.ventana_coincidencia_s && <span className="error-campo">{errores.ventana_coincidencia_s}</span>}
        </div>
        <div className="campo">
          <label htmlFor="aj-rebote">Antirrebote (segundos)</label>
          <input id="aj-rebote" type="number" min="0" max="60" value={a.antirrebote_s} onChange={set("antirrebote_s")} aria-invalid={!!errores.antirrebote_s} aria-describedby="aj-rebote-ayuda" />
          <span className="ayuda" id="aj-rebote-ayuda">Ignora la misma credencial repetida en este tiempo. Por defecto 3 s.</span>
          {errores.antirrebote_s && <span className="error-campo">{errores.antirrebote_s}</span>}
        </div>
        <div className="campo">
          <label htmlFor="aj-umbral">Confianza mínima de la patente</label>
          <input id="aj-umbral" type="number" step="0.05" min="0" max="1" value={a.umbral_confianza_patente} onChange={set("umbral_confianza_patente")} aria-invalid={!!errores.umbral_confianza_patente} aria-describedby="aj-umbral-ayuda" />
          <span className="ayuda" id="aj-umbral-ayuda">Lecturas de cámara por debajo de este valor no abren. Por defecto 0,85.</span>
          {errores.umbral_confianza_patente && <span className="error-campo">{errores.umbral_confianza_patente}</span>}
        </div>
        <label className="chk">
          <input type="checkbox" checked={a.anti_passback} onChange={set("anti_passback")} aria-describedby="aj-ap-ayuda" />
          Anti-passback
        </label>
        <p className="ayuda" id="aj-ap-ayuda">Sólo funciona si el lector informa la dirección (entrada o salida). Impide entrar dos veces seguidas sin salir.</p>
      </div>
      <div className="acciones"><button className="btn" disabled={busy}>Guardar ajustes</button></div>
      {msg && <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>}
    </form>
    <ClaveLectores api={api} />
    </>
  );
}
