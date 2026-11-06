"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Icono from "./Icono";

export const fh = (iso) => (iso ? new Date(iso).toLocaleString("es-CL", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "");
export const fd = (iso) => (iso ? new Date(iso).toLocaleDateString("es-CL", { day: "2-digit", month: "short" }) : "");
export const hoyISO = () => new Date().toISOString().slice(0, 10);

// Carga una lista y expone recargar(); el error queda como texto, no como excepción.
export function useLista(cargarFn, dep = []) {
  const [lista, setLista] = useState(null);
  const [err, setErr] = useState("");
  const fn = useRef(cargarFn);
  fn.current = cargarFn;
  const claves = dep.filter((d) => typeof d !== "function"); // las funciones del cliente cambian en cada render del padre
  const recargar = useCallback(async () => {
    try { setLista(await fn.current()); setErr(""); } catch (e) { setErr(e.message); setLista((l) => l ?? []); }
  }, claves); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { recargar(); }, [recargar]);
  return [lista, recargar, err];
}

// Mensaje de resultado: el estado se dice con icono y texto, no sólo con color.
export function Estado({ msg }) {
  if (!msg) return null;
  return (
    <p role={msg.ok ? "status" : "alert"} className={`aviso ${msg.ok ? "ok" : "err"}`}>
      <Icono n={msg.ok ? "ok" : "alerta"} />{msg.t}
    </p>
  );
}

export function Cargando({ filas = 3 }) {
  return <div className="esqueleto" aria-busy="true" aria-label="Cargando">{Array.from({ length: filas }, (_, i) => <span key={i} />)}</div>;
}

// Confirmación en línea: sustituye a window.confirm/prompt. `children` son los campos extra (p. ej. el motivo).
export function Confirmar({ pregunta, etiqueta, peligro, deshabilitado, onConfirmar, onCancelar, children }) {
  return (
    <form className="confirmar" onSubmit={(e) => { e.preventDefault(); onConfirmar(); }}>
      <span>{pregunta}</span>
      {children}
      <button className={peligro ? "btn peligro" : "btn"} disabled={deshabilitado}>{etiqueta}</button>
      <button type="button" className="btn sec" onClick={onCancelar}>Cancelar</button>
    </form>
  );
}
