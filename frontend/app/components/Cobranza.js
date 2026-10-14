import { useState } from "react";
import { clp } from "../../lib/api";

export default function Cobranza({ cob, api, onChange }) {
  const [sel, setSel] = useState(new Set());
  const [canales, setCanales] = useState({ whatsapp: true, email: true });
  const [extra, setExtra] = useState("");
  const [msg, setMsg] = useState(null);
  const [busy, setBusy] = useState(false);
  const toggle = (id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const todos = sel.size === cob.morosos.length && sel.size > 0;
  const enviar = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await api.recordatorios({ unidad_ids: sel.size ? [...sel] : null, canales: Object.keys(canales).filter((c) => canales[c]), mensaje_extra: extra });
      setMsg({ ok: true, t: `${r.unidades} departamento(s): ${r.whatsapp} por WhatsApp, ${r.email} por correo.${r.sin_contacto.length ? " Sin contacto: " + r.sin_contacto.join(", ") + "." : ""}` });
      await onChange();
    } catch (e) { setMsg({ ok: false, t: e.message }); }
    setBusy(false);
  };
  return (
    <div className="cobranza-vista">
      <header className="vista-cab">
        <h2>Cobranza</h2>
        <p>{cob.morosos.length} departamentos con saldo, {clp(cob.total)} en total. Los pagos se registran en su sistema actual; aquí sólo se avisa a los residentes.</p>
      </header>
      {cob.morosos.length === 0 ? <p className="vacio">Nadie tiene saldo pendiente.</p> : (
        <>
          <table className="tabla">
            <thead><tr>
              <th><input type="checkbox" aria-label="Seleccionar todos" checked={todos} onChange={() => setSel(todos ? new Set() : new Set(cob.morosos.map((m) => m.unidad_id)))} /></th>
              <th>Depto</th><th className="der">Saldo</th><th className="der">Atraso</th><th>Código de pago</th>
            </tr></thead>
            <tbody>{cob.morosos.map((m) => (
              <tr key={m.unidad_id} className={m.dias_atraso > 60 ? "grave" : ""}>
                <td><input type="checkbox" aria-label={`Seleccionar ${m.numero}`} checked={sel.has(m.unidad_id)} onChange={() => toggle(m.unidad_id)} /></td>
                <td className="n">{m.numero}</td><td className="der">{clp(m.deuda)}</td>
                <td className="der">{m.dias_atraso > 0 ? `${m.dias_atraso} días` : "vigente"}</td><td><code>{m.codigo_cobro}</code></td>
              </tr>))}</tbody>
          </table>
          <div className="envio">
            <fieldset><legend>Canal</legend>
              {["whatsapp", "email"].map((c) => (
                <label key={c} className="chk"><input type="checkbox" checked={canales[c]} onChange={() => setCanales({ ...canales, [c]: !canales[c] })} />{c === "email" ? "Correo" : "WhatsApp"}</label>))}
            </fieldset>
            <label className="grande">Nota al final del mensaje (opcional)
              <input value={extra} onChange={(e) => setExtra(e.target.value)} maxLength={200} placeholder="Si ya pagó, ignore este aviso." /></label>
            <button className="btn" disabled={busy || !Object.values(canales).some(Boolean)} onClick={enviar}>
              {sel.size ? `Enviar a ${sel.size} seleccionado${sel.size > 1 ? "s" : ""}` : `Enviar a los ${cob.morosos.length}`}
            </button>
          </div>
        </>
      )}
      {msg && <p role="status" className={`aviso ${msg.ok ? "ok" : "err"}`}>{msg.t}</p>}
    </div>
  );
}
