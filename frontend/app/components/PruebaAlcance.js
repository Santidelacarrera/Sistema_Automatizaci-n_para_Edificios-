import { useEffect, useRef, useState } from "react";
import { mensajeError } from "../../lib/validar";

const hora = (iso) => new Date(iso).toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
const RESULTADOS = [["leyo", "Leyó"], ["parcial", "Leyó a veces"], ["no_leyo", "No leyó"]];

// Herramienta para el técnico: camina con el sticker y anota desde qué distancia el portón deja de leer.
export default function PruebaAlcance({ api }) {
  const [lecturas, setLecturas] = useState([]);
  const [pruebas, setPruebas] = useState([]);
  const [distancia, setDistancia] = useState("");
  const [resultado, setResultado] = useState("leyo");
  const [uid, setUid] = useState("");
  const [nota, setNota] = useState("");
  const [errores, setErrores] = useState({});
  const [msg, setMsg] = useState(null);
  const uidAuto = useRef(true);

  const refrescar = async () => {
    try {
      const todas = await api.accesos();
      setLecturas(todas.filter((a) => a.punto === "vehicular").slice(0, 6));
      const ultimoSticker = todas.find((a) => a.fuente === "sticker");
      if (ultimoSticker && uidAuto.current) setUid(ultimoSticker.token);
    } catch (e) { setMsg({ ok: false, t: mensajeError(e.detail ?? e.message) }); }
  };
  useEffect(() => {
    refrescar();
    api.pruebasAlcance().then(setPruebas).catch(() => {});
    const t = setInterval(refrescar, 1000);
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const anotar = async (e) => {
    e.preventDefault();
    const err = {};
    const d = Number(distancia);
    if (distancia === "" || Number.isNaN(d) || d < 0 || d > 50) err.distancia = "Indica la distancia en metros, entre 0 y 50.";
    setErrores(err);
    if (Object.keys(err).length) { setMsg({ ok: false, t: "Falta la distancia." }); return; }
    try {
      await api.anotarPruebaAlcance({ distancia_m: d, resultado, tag_uid: uid.trim(), nota: nota.trim() });
      setMsg({ ok: true, t: `Anotado: ${d.toLocaleString("es-CL")} m, ${RESULTADOS.find((r) => r[0] === resultado)[1].toLowerCase()}.` });
      setDistancia(""); setNota("");
      setPruebas(await api.pruebasAlcance());
    } catch (x) { setMsg({ ok: false, t: mensajeError(x.detail ?? x.message) }); }
  };

  const ultima = lecturas[0];
  return (
    <div className="alcance-vista">
      <header className="vista-cab">
        <h2>Prueba de alcance</h2>
        <p>Camine despacio con el sticker hacia el lector. Anote la distancia en la que el portón deja de reaccionar. Esta pantalla se actualiza sola cada segundo.</p>
      </header>

      <section className="alcance-vivo" aria-labelledby="vivo-titulo">
        <h3 id="vivo-titulo">Lecturas en vivo</h3>
        <p className="ultima" aria-live="polite">
          {ultima ? <><b>{ultima.permitido ? "Abrió" : "No abrió"}</b> · {hora(ultima.creado)} · {ultima.motivo}</> : "Sin lecturas todavía."}
        </p>
        <ul className="lecturas-vivo" aria-label="Últimas lecturas del portón">
          {lecturas.map((a) => (
            <li key={a.id} className={a.permitido ? "pasa" : "niega"}>
              <time>{hora(a.creado)}</time> <span>{a.fuente || "lectura"}</span> <span>{a.permitido ? "abrió" : "no abrió"}</span>
            </li>
          ))}
        </ul>
      </section>

      <form className="form-admin" onSubmit={anotar} noValidate aria-labelledby="anotar-titulo">
        <h3 id="anotar-titulo">Anotar en la bitácora</h3>
        <div className="grilla-form">
          <div className="campo">
            <label htmlFor="al-dist">Distancia (metros)</label>
            <input id="al-dist" type="number" step="0.5" min="0" max="50" inputMode="decimal" value={distancia}
              onChange={(e) => setDistancia(e.target.value)} aria-invalid={!!errores.distancia} aria-describedby="al-dist-ayuda" />
            <span className="ayuda" id="al-dist-ayuda">Mida desde el lector hasta el parabrisas.</span>
            {errores.distancia && <span className="error-campo">{errores.distancia}</span>}
          </div>
          <fieldset className="campo">
            <legend>Resultado</legend>
            <div className="radios-fila">
              {RESULTADOS.map(([v, t]) => (
                <label key={v} className="chk"><input type="radio" name="resultado" value={v} checked={resultado === v} onChange={(e) => setResultado(e.target.value)} />{t}</label>
              ))}
            </div>
          </fieldset>
          <div className="campo">
            <label htmlFor="al-uid">Código del sticker</label>
            <input id="al-uid" value={uid} onChange={(e) => { uidAuto.current = false; setUid(e.target.value); }} placeholder="Se completa con la última lectura" maxLength={40} />
          </div>
          <div className="campo">
            <label htmlFor="al-nota">Nota (opcional)</label>
            <input id="al-nota" value={nota} onChange={(e) => setNota(e.target.value)} maxLength={200} placeholder="Ej.: lluvia, parabrisas metalizado" />
          </div>
        </div>
        <div className="acciones"><button className="btn">Anotar en la bitácora</button></div>
        {msg && <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>}
      </form>

      <section aria-labelledby="bitacora-titulo">
        <h3 id="bitacora-titulo">Pruebas anotadas</h3>
        {pruebas.length === 0 && <p className="vacio">Todavía no hay pruebas anotadas.</p>}
        {pruebas.length > 0 && (
          <table className="tabla">
            <thead><tr><th>Hora</th><th className="der">Distancia</th><th>Resultado</th><th>Sticker</th><th>Nota</th></tr></thead>
            <tbody>{pruebas.map((p) => (
              <tr key={p.id}>
                <td>{hora(p.creado)}</td><td className="der">{Number(p.distancia_m).toLocaleString("es-CL")} m</td>
                <td>{RESULTADOS.find((r) => r[0] === p.resultado)?.[1] || p.resultado}</td>
                <td><code>{p.tag ? "…" + p.tag.slice(-8) : "—"}</code></td><td>{p.nota || "—"}</td>
              </tr>))}</tbody>
          </table>
        )}
      </section>
    </div>
  );
}
