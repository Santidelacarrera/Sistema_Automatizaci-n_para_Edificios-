"use client";
import { useState } from "react";
import { clp } from "../../lib/api";
import { Cargando, Confirmar, Estado, fh, useLista } from "./ui";
import Icono from "./Icono";

const CAT = { aviso: "Aviso", mantencion: "Mantención", asamblea: "Asamblea", urgente: "Urgente" };
const TRANSPORTISTAS = ["Chilexpress", "Mercado Libre", "Correos de Chile", "Starken", "Blue Express"];

export function Encomiendas({ api, data }) {
  const [lista, recargar, err] = useLista(() => api.encomiendas(), [api.encomiendas]);
  const [f, setF] = useState({ unidad_id: "", transportista: "", descripcion: "" });
  const [msg, setMsg] = useState(null);
  const [entregando, setEntregando] = useState(null);
  const [quien, setQuien] = useState("");

  const registrar = async (e) => {
    e.preventDefault(); setMsg(null);
    try {
      await api.recibirEncomienda({ ...f, unidad_id: Number(f.unidad_id) });
      setF({ unidad_id: "", transportista: "", descripcion: "" });
      setMsg({ ok: true, t: "Encomienda registrada. El residente recibe el aviso." }); await recargar();
    } catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const entregar = async () => {
    try {
      await api.entregarEncomienda(entregando, quien.trim());
      setMsg({ ok: true, t: "Entrega registrada con fecha y hora." }); setEntregando(null); setQuien(""); await recargar();
    } catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const pendientes = (lista || []).filter((x) => x.estado === "pendiente").length;

  return (
    <section aria-labelledby="h-enc">
      <h3 id="h-enc">Encomiendas{lista ? <span className="cuenta">{pendientes} por retirar</span> : null}</h3>
      <form className="fila-form" onSubmit={registrar}>
        <label>Departamento
          <select value={f.unidad_id} onChange={(e) => setF({ ...f, unidad_id: e.target.value })} required>
            <option value="">Elegir</option>
            {data.unidades.map((u) => <option key={u.id} value={u.id}>{u.numero}</option>)}
          </select></label>
        <label>Transportista
          <input list="transportistas" value={f.transportista} onChange={(e) => setF({ ...f, transportista: e.target.value })} maxLength={60} autoComplete="off" />
          <datalist id="transportistas">{TRANSPORTISTAS.map((t) => <option key={t} value={t} />)}</datalist></label>
        <label className="ancho">Detalle
          <input value={f.descripcion} onChange={(e) => setF({ ...f, descripcion: e.target.value })} maxLength={200} placeholder="Caja mediana, sobre, bulto grande…" /></label>
        <button className="btn" disabled={!f.unidad_id}>Registrar encomienda</button>
      </form>
      <Estado msg={msg} />{err && <Estado msg={{ ok: false, t: err }} />}
      {!lista ? <Cargando /> : lista.length === 0 ? (
        <p className="vacio">Aún no hay encomiendas. Al registrar la primera, el residente la ve en su portal y recibe un WhatsApp.</p>
      ) : (
        <table className="tabla">
          <thead><tr><th>Depto</th><th>Paquete</th><th>Llegó</th><th>Estado</th><th><span className="solo-lector">Acciones</span></th></tr></thead>
          <tbody>{lista.map((e) => (
            <tr key={e.id} className={e.estado === "entregada" ? "hecho" : ""}>
              <td className="num">{e.unidad}</td>
              <td><span className="con-icono"><Icono n="paquete" />{e.transportista || "Sin transportista"}</span>{e.descripcion ? <small>{e.descripcion}</small> : null}</td>
              <td>{fh(e.recibida_at)}</td>
              <td>{e.estado === "entregada" ? <>Retiró {e.retirada_por}<small>{fh(e.entregada_at)}</small></> : "Por retirar"}</td>
              <td className="acc">{e.estado === "pendiente" && entregando !== e.id && <button className="mini" onClick={() => { setEntregando(e.id); setQuien(""); setMsg(null); }}>Entregar</button>}</td>
            </tr>))}</tbody>
        </table>)}
      {entregando && (
        <Confirmar pregunta="Quien firma el retiro:" etiqueta="Confirmar entrega" deshabilitado={quien.trim().length < 2}
          onConfirmar={entregar} onCancelar={() => setEntregando(null)}>
          <input aria-label="Nombre de quien retira" value={quien} onChange={(e) => setQuien(e.target.value)} maxLength={120} autoFocus />
        </Confirmar>)}
    </section>
  );
}

export function Comunicados({ api }) {
  const [lista, recargar, err] = useLista(() => api.comunicados(), [api.comunicados]);
  const vacio = { titulo: "", cuerpo: "", categoria: "aviso", fijado: false };
  const [f, setF] = useState(vacio);
  const [msg, setMsg] = useState(null);
  const [retirando, setRetirando] = useState(null);

  const publicar = async (e) => {
    e.preventDefault(); setMsg(null);
    try { await api.publicarComunicado(f); setF(vacio); setMsg({ ok: true, t: "Comunicado publicado en el muro." }); await recargar(); }
    catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  const fijar = async (c) => { try { await api.editarComunicado(c.id, { fijado: !c.fijado }); await recargar(); } catch (x) { setMsg({ ok: false, t: x.message }); } };
  const retirar = async () => { try { await api.retirarComunicado(retirando.id); setRetirando(null); await recargar(); } catch (x) { setMsg({ ok: false, t: x.message }); } };

  return (
    <section aria-labelledby="h-com">
      <h3 id="h-com">Comunicados</h3>
      <form className="fila-form" onSubmit={publicar}>
        <label className="ancho">Título<input value={f.titulo} onChange={(e) => setF({ ...f, titulo: e.target.value })} minLength={3} maxLength={160} required /></label>
        <label>Tipo
          <select value={f.categoria} onChange={(e) => setF({ ...f, categoria: e.target.value })}>
            {Object.entries(CAT).map(([k, t]) => <option key={k} value={k}>{t}</option>)}</select></label>
        <label className="completo">Mensaje<textarea value={f.cuerpo} onChange={(e) => setF({ ...f, cuerpo: e.target.value })} maxLength={4000} rows={3} required /></label>
        <label className="chk"><input type="checkbox" checked={f.fijado} onChange={(e) => setF({ ...f, fijado: e.target.checked })} />Mantener arriba del muro</label>
        <button className="btn">Publicar comunicado</button>
      </form>
      <Estado msg={msg} />{err && <Estado msg={{ ok: false, t: err }} />}
      {!lista ? <Cargando /> : lista.length === 0 ? (
        <p className="vacio">El muro está vacío. Publica cortes de agua, mantenciones o citaciones a asamblea y los residentes los leen en Mi depto.</p>
      ) : (
        <ul className="items">{lista.map((c) => (
          <li key={c.id}>
            <div className="items-cab">
              <b>{c.fijado ? <Icono n="fijar" titulo="Fijado" /> : null} {c.titulo}</b>
              <span className={`etq etq-${c.categoria}`}>{CAT[c.categoria]}</span>
              <time dateTime={c.publicado_at}>{fh(c.publicado_at)}</time>
            </div>
            <p>{c.cuerpo}</p>
            <div className="acc">
              <button className="mini" onClick={() => fijar(c)}>{c.fijado ? "Quitar de arriba" : "Mantener arriba"}</button>
              <button className="mini" onClick={() => setRetirando(c)}>Retirar</button>
            </div>
          </li>))}</ul>)}
      {retirando && <Confirmar pregunta={`¿Retirar «${retirando.titulo}» del muro?`} etiqueta="Retirar comunicado" peligro onConfirmar={retirar} onCancelar={() => setRetirando(null)} />}
    </section>
  );
}

export function AvisosPago({ api, onChange }) {
  const [lista, recargar, err] = useLista(() => api.avisosPago(), [api.avisosPago]);
  const [msg, setMsg] = useState(null);
  const [rechazando, setRechazando] = useState(null);
  const [motivo, setMotivo] = useState("");

  const resolver = async (a, aprobar) => {
    try {
      const r = await api.resolverAviso(a.id, aprobar, aprobar ? "" : motivo.trim());
      setMsg({ ok: true, t: !aprobar ? "Aviso rechazado; el residente verá el motivo."
        : r.ya_conciliado ? `La cartola ya había abonado ${clp(a.monto)} al depto ${a.unidad}; no se abonó de nuevo.` : `Se abonaron ${clp(a.monto)} al depto ${a.unidad}.` });
      setRechazando(null); setMotivo(""); await recargar(); onChange?.();
    } catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  return (
    <section aria-labelledby="h-av">
      <h3 id="h-av">Transferencias avisadas por residentes</h3>
      <Estado msg={msg} />{err && <Estado msg={{ ok: false, t: err }} />}
      {!lista ? <Cargando /> : lista.length === 0 ? (
        <p className="vacio">Ningún residente ha avisado una transferencia. Cuando lo hagan, aparecerá aquí para aprobarla.</p>
      ) : (
        <table className="tabla">
          <thead><tr><th>Depto</th><th className="der">Monto</th><th>Banco y operación</th><th>Estado</th><th><span className="solo-lector">Acciones</span></th></tr></thead>
          <tbody>{lista.map((a) => (
            <tr key={a.id} className={a.estado !== "pendiente" ? "hecho" : ""}>
              <td className="num">{a.unidad}</td><td className="der">{clp(a.monto)}</td>
              <td>{a.banco}<small>Operación {a.nro_operacion}</small></td>
              <td>{{ pendiente: "Por revisar", aprobado: "Aprobado", rechazado: "Rechazado" }[a.estado]}{a.motivo ? <small>{a.motivo}</small> : null}</td>
              <td className="acc">{a.estado === "pendiente" && (<>
                <button className="mini" onClick={() => resolver(a, true)}>Aprobar y abonar</button>
                <button className="mini" onClick={() => { setRechazando(a); setMotivo(""); }}>Rechazar</button></>)}</td>
            </tr>))}</tbody>
        </table>)}
      {rechazando && (
        <Confirmar pregunta={`Rechazar el aviso del depto ${rechazando.unidad}. Motivo:`} etiqueta="Rechazar aviso" peligro
          deshabilitado={!motivo.trim()} onConfirmar={() => resolver(rechazando, false)} onCancelar={() => setRechazando(null)}>
          <input aria-label="Motivo del rechazo" value={motivo} onChange={(e) => setMotivo(e.target.value)} maxLength={200} autoFocus />
        </Confirmar>)}
    </section>
  );
}

export function Espacios({ api }) {
  const [lista, recargar, err] = useLista(() => api.espacios(), [api.espacios]);
  const [edit, setEdit] = useState(null);
  const [msg, setMsg] = useState(null);
  const guardar = async (e) => {
    e.preventDefault();
    try {
      await api.editarEspacio(edit.id, { tarifa: Number(edit.tarifa), aforo: Number(edit.aforo) });
      setMsg({ ok: true, t: `${edit.nombre}: tarifa y aforo guardados.` }); setEdit(null); await recargar();
    } catch (x) { setMsg({ ok: false, t: x.message }); }
  };
  return (
    <section aria-labelledby="h-esp">
      <h3 id="h-esp">Espacios comunes</h3>
      <Estado msg={msg} />{err && <Estado msg={{ ok: false, t: err }} />}
      {!lista ? <Cargando filas={2} /> : lista.length === 0 ? <p className="vacio">No hay espacios comunes configurados.</p> : (
        <table className="tabla">
          <thead><tr><th>Espacio</th><th className="der">Tarifa de uso</th><th className="der">Aforo</th><th><span className="solo-lector">Acciones</span></th></tr></thead>
          <tbody>{lista.map((e) => (
            <tr key={e.id}><td>{e.nombre}</td><td className="der">{e.tarifa ? clp(e.tarifa) : "Sin costo"}</td>
              <td className="der">{e.aforo ? `${e.aforo} personas` : "Sin límite"}</td>
              <td className="acc"><button className="mini" onClick={() => { setEdit({ ...e }); setMsg(null); }}>Editar</button></td></tr>))}</tbody>
        </table>)}
      {edit && (
        <form className="fila-form" onSubmit={guardar}>
          <b className="fila-titulo">{edit.nombre}</b>
          <label>Tarifa de uso (CLP)<input type="number" min="0" step="500" value={edit.tarifa} onChange={(e) => setEdit({ ...edit, tarifa: e.target.value })} required /></label>
          <label>Aforo (0 = sin límite)<input type="number" min="0" max="1000" value={edit.aforo} onChange={(e) => setEdit({ ...edit, aforo: e.target.value })} required /></label>
          <button className="btn">Guardar</button>
          <button type="button" className="btn sec" onClick={() => setEdit(null)}>Cancelar</button>
        </form>)}
      <p className="nota">La tarifa se carga sola al gasto común de quien reserva. El horario permitido se define en Administración, en Reglas.</p>
    </section>
  );
}

export default function Comunidad({ api, data, esAdmin, onChange }) {
  return (
    <div className="seccion-vista">
      <header className="vista-cab"><h2>Conserjería</h2>
        <p>{esAdmin ? "Paquetes de recepción, avisos oficiales, transferencias que informan los residentes y espacios comunes." : "Registro y entrega de paquetes."}</p></header>
      <Encomiendas api={api} data={data} />
      {esAdmin && <Comunicados api={api} />}
      {esAdmin && <AvisosPago api={api} onChange={onChange} />}
      {esAdmin && <Espacios api={api} />}
    </div>
  );
}
