"use client";
import { useState } from "react";
import { clp } from "../../lib/api";
import { Cargando, Confirmar, Estado, hoyISO, useLista } from "./ui";

const mesActual = () => hoyISO().slice(0, 7);

export function Resumen({ api, refresco }) {
  const [r, , err] = useLista(() => api.resumenFinanzas(), [api.resumenFinanzas, refresco]);
  if (err) return <Estado msg={{ ok: false, t: err }} />;
  if (!r) return <Cargando filas={1} />;
  return (
    <dl className="datos" aria-label="Resumen de morosidad">
      <div><dt>Deuda total</dt><dd>{clp(r.deuda_total)}</dd></div>
      <div><dt>Deuda vencida</dt><dd>{clp(r.deuda_vencida)}</dd></div>
      <div><dt>Departamentos morosos</dt><dd>{r.unidades_morosas} de {r.unidades} ({String(r.morosidad_pct).replace(".", ",")} %)</dd></div>
      <div><dt>Transferencias por revisar</dt><dd>{r.avisos_pago_pendientes}</dd></div>
    </dl>
  );
}

export function Morosidad({ api, onChange }) {
  const [tasa, setTasa] = useState("1.5");
  const [periodo, setPeriodo] = useState(mesActual());
  const [confirmando, setConfirmando] = useState(false);
  const [msg, setMsg] = useState(null);
  const aplicar = async () => {
    try {
      const r = await api.cobrarIntereses({ tasa_mensual_pct: Number(tasa), periodo });
      setMsg({ ok: true, t: r.unidades ? `Interés cargado a ${r.unidades} departamento(s): ${clp(r.total)} en total.${r.ya_aplicados ? ` ${r.ya_aplicados} ya lo tenían.` : ""}` : "No había nada que cargar: nadie con deuda vencida sin interés de este mes." });
      setConfirmando(false); onChange?.();
    } catch (x) { setMsg({ ok: false, t: x.message }); setConfirmando(false); }
  };
  return (
    <section aria-labelledby="h-mor">
      <h3 id="h-mor">Intereses por mora</h3>
      <div className="fila-form">
        <label>Mes al que se carga<input type="month" value={periodo} onChange={(e) => setPeriodo(e.target.value)} required /></label>
        <label>Interés mensual (%)<input type="number" min="0.1" max="10" step="0.1" value={tasa} onChange={(e) => setTasa(e.target.value)} /></label>
        <button className="btn sec" disabled={!(Number(tasa) > 0) || !periodo} onClick={() => { setConfirmando(true); setMsg(null); }}>Cargar intereses</button>
      </div>
      {confirmando && <Confirmar pregunta={`Se cargará ${tasa} % sobre el capital vencido de cada departamento.`} etiqueta="Cargar intereses" onConfirmar={aplicar} onCancelar={() => setConfirmando(false)} />}
      <Estado msg={msg} />
      <p className="nota">Se calcula sobre la deuda vencida, sin interés sobre interés. Repetirlo para el mismo mes no duplica el cargo.</p>
    </section>
  );
}
