"use client";
import { useState } from "react";
import Placa from "./Placa";
import { clp } from "../../lib/api";

const ENCOMIENDAS_EJEMPLO = [
  { id: 1, courier: "MercadoLibre", detalle: "Paquete mediano (caja)", recepcion: "Hoy 11:20", estado: "pendiente" },
  { id: 2, courier: "Chilexpress", detalle: "Sobre documentos", recepcion: "Ayer 16:45", estado: "retirado" },
];

const COMUNICADOS_EJEMPLO = [
  { id: 1, titulo: "Mantención preventiva de ascensores Torre Norte", fecha: "Hoy", categoria: "Mantención", urgente: true, cuerpo: "Este jueves de 10:00 a 13:00 se realizará mantención al ascensor 2. El ascensor 1 permanecerá 100% operativo." },
  { id: 2, titulo: "Asamblea Ordinaria de Copropietarios 2026", fecha: "28 Oct", categoria: "Comunidad", urgente: false, cuerpo: "Se convoca a todos los propietarios a la asamblea en la Sala Multiuso a las 19:30 hrs para revisión de balance." },
  { id: 3, titulo: "Recordatorio: Horarios de uso de Quinchos y Piscina", fecha: "15 Oct", categoria: "Normativa", urgente: false, cuerpo: "Los quinchos deben ser reservados con al menos 24 hrs de anticipación a través del sistema." },
];

export default function PortalPropietario({ data, api, sess, deptoInicial }) {
  const unidades = data.unidades || [];
  const [deptoId, setDeptoId] = useState(deptoInicial || (unidades[0] ? unidades[0].id : null));
  const [tabInterno, setTabInterno] = useState("gastos"); // gastos | visitas | encomiendas | comunicados | vehiculos
  const [comprobanteEnviado, setComprobanteEnviado] = useState(false);
  const [pagoForm, setPagoForm] = useState({ banco: "Banco de Chile", nro: "", monto: "" });
  const [visitaForm, setVisitaForm] = useState({ nombre: "", rut: "", patente: "", fecha: "" });
  const [visitaQr, setVisitaQr] = useState(null);
  const [encomiendas, setEncomiendas] = useState(ENCOMIENDAS_EJEMPLO);

  const unidad = unidades.find((u) => u.id === deptoId) || unidades[0];

  if (!unidad) return <p className="vacio">No hay unidades disponibles en este edificio.</p>;

  const titular = (unidad.residentes && unidad.residentes[0]) ? unidad.residentes[0] : { nombre: "Propietario / Residente" };
  const alDia = !unidad.deuda || unidad.deuda === 0;

  const notificarPago = (e) => {
    e.preventDefault();
    setComprobanteEnviado(true);
    setTimeout(() => setComprobanteEnviado(false), 5000);
  };

  const generarVisita = (e) => {
    e.preventDefault();
    if (!visitaForm.nombre) return;
    setVisitaQr({
      nombre: visitaForm.nombre,
      patente: visitaForm.patente,
      codigo: "QR-" + Math.random().toString(36).substring(2, 8).toUpperCase(),
    });
  };

  const marcarRetiroEncomienda = (id) => {
    setEncomiendas(encomiendas.map((enc) => enc.id === id ? { ...enc, estado: "retirado" } : enc));
  };

  return (
    <div className="portal-propietario">
      {/* Selector superior de departamento (útil para administradores o propietarios con más de 1 unidad) */}
      <div className="portal-header-card">
        <div className="portal-bienvenida">
          <span className="portal-badge-rol">Portal del Copropietario</span>
          <h2>Departamento {unidad.numero}</h2>
          <p className="portal-subtitulo">{data.edificio.nombre} · Titular: <b>{titular.nombre}</b></p>
        </div>
        <div className="portal-depto-selector">
          <label htmlFor="selector-mi-depto">Cambiar departamento:</label>
          <select id="selector-mi-depto" value={unidad.id} onChange={(e) => { setDeptoId(Number(e.target.value)); setVisitaQr(null); }}>
            {unidades.map((u) => (
              <option key={u.id} value={u.id}>Depto {u.numero} ({u.deuda > 0 ? "Saldo pendiente" : "Al día"})</option>
            ))}
          </select>
        </div>
      </div>

      {/* Navegación por pestañas del portal */}
      <nav className="portal-tabs" aria-label="Secciones del propietario">
        <button className={`portal-tab ${tabInterno === "gastos" ? "on" : ""}`} onClick={() => setTabInterno("gastos")}>
          💳 Gastos Comunes
        </button>
        <button className={`portal-tab ${tabInterno === "visitas" ? "on" : ""}`} onClick={() => setTabInterno("visitas")}>
          🎟️ Pases de Visita QR
        </button>
        <button className={`portal-tab ${tabInterno === "encomiendas" ? "on" : ""}`} onClick={() => setTabInterno("encomiendas")}>
          📦 Encomiendas {encomiendas.filter((x) => x.estado === "pendiente").length > 0 && <span className="p-badge">{encomiendas.filter((x) => x.estado === "pendiente").length}</span>}
        </button>
        <button className={`portal-tab ${tabInterno === "comunicados" ? "on" : ""}`} onClick={() => setTabInterno("comunicados")}>
          📢 Avisos del Edificio
        </button>
        <button className={`portal-tab ${tabInterno === "vehiculos" ? "on" : ""}`} onClick={() => setTabInterno("vehiculos")}>
          🚗 Mis Vehículos y Tags
        </button>
      </nav>

      {/* 1. SECCIÓN GASTOS COMUNES (ESTILO EDIFITO) */}
      {tabInterno === "gastos" && (
        <div className="portal-grid-gastos">
          <div className="card-principal-gasto">
            <div className="card-cabecera">
              <div>
                <span className="periodo-tag">Período Actual: Noviembre 2026</span>
                <h3>Estado de Cuenta</h3>
              </div>
              <span className={`estado-pago-pill ${alDia ? "pill-al-dia" : "pill-deudor"}`}>
                {alDia ? "✓ Cuenta al día" : "⚠️ Saldo pendiente"}
              </span>
            </div>

            <div className="monto-destacado-wrap">
              <span className="monto-label">Total a Pagar este mes</span>
              <div className="monto-valor">{alDia ? clp(0) : clp(unidad.deuda)}</div>
              <p className="vencimiento-nota">
                {alDia ? "No registra cobros pendientes a la fecha." : `Vence el 05 de Noviembre de 2026. ${unidad.vencida > 0 ? "Incluye recargo de meses anteriores." : ""}`}
              </p>
            </div>

            {/* Desglose tipo colilla de Edifito */}
            <div className="desglose-colilla">
              <h4>Detalle de Gastos Comunes</h4>
              <div className="fila-detalle">
                <span>Gasto Común Ordinario (prorrateo)</span>
                <b>{clp(alDia ? 78400 : Math.round(unidad.deuda * 0.75))}</b>
              </div>
              <div className="fila-detalle">
                <span>Aporte a Fondo de Reserva (5%)</span>
                <b>{clp(alDia ? 5200 : Math.round(unidad.deuda * 0.1))}</b>
              </div>
              <div className="fila-detalle">
                <span>Consumo de Agua Caliente / Caldera</span>
                <b>{clp(alDia ? 14200 : Math.round(unidad.deuda * 0.15))}</b>
              </div>
              {unidad.vencida > 0 && (
                <div className="fila-detalle deuda-anterior">
                  <span>Saldo Anterior Vencido</span>
                  <b>{clp(unidad.vencida)}</b>
                </div>
              )}
              <div className="fila-total">
                <span>Total Liquidación del Mes</span>
                <b>{alDia ? clp(97800) : clp(unidad.deuda)}</b>
              </div>
            </div>

            <div className="acciones-colilla">
              <button type="button" className="btn-secundario" onClick={() => alert("Descargando colilla oficial en formato PDF...")}>
                📄 Descargar Colilla (PDF)
              </button>
            </div>
          </div>

          {/* Formulario de notificación de pago */}
          <div className="card-notificar-pago">
            <h3>Notificar Transferencia Bancaria</h3>
            <p className="nota-pago">
              Si ya realizaste tu transferencia a la cuenta del edificio, regístrala aquí para que la administración la concilie.
            </p>

            {comprobanteEnviado ? (
              <div className="aviso-exito-pago">
                <b>✓ Comprobante recibido con éxito</b>
                <p>La administración conciliará el abono contra la cartola bancaria en las próximas horas.</p>
              </div>
            ) : (
              <form onSubmit={notificarPago} className="form-notificar">
                <label>
                  Banco Origen:
                  <select value={pagoForm.banco} onChange={(e) => setPagoForm({ ...pagoForm, banco: e.target.value })}>
                    <option>Banco de Chile</option>
                    <option>Banco Estado</option>
                    <option>Santander</option>
                    <option>BCI</option>
                    <option>Scotiabank</option>
                    <option>Itaú</option>
                  </select>
                </label>
                <label>
                  N° Operación / Transacción:
                  <input
                    type="text"
                    required
                    placeholder="Ej: 98451203"
                    value={pagoForm.nro}
                    onChange={(e) => setPagoForm({ ...pagoForm, nro: e.target.value })}
                  />
                </label>
                <label>
                  Monto Transferido (CLP):
                  <input
                    type="number"
                    required
                    placeholder={alDia ? "97800" : String(unidad.deuda)}
                    value={pagoForm.monto}
                    onChange={(e) => setPagoForm({ ...pagoForm, monto: e.target.value })}
                  />
                </label>
                <button type="submit" className="btn-primario-grande">
                  Confirmar y Enviar Comprobante
                </button>
              </form>
            )}

            <div className="datos-transferencia-box">
              <b>Datos Bancarios del Edificio:</b>
              <p>Comunidad Edificio {data.edificio.nombre}<br />RUT: 65.123.456-7<br />Banco Santander - Cta Cte: 0-000-8451234-9<br />Email: pagos@{data.edificio.id}.cl</p>
            </div>
          </div>
        </div>
      )}

      {/* 2. SECCIÓN PASES DE VISITAS CON QR */}
      {tabInterno === "visitas" && (
        <div className="portal-visitas-wrap">
          <div className="card-generar-visita">
            <h3>Generar Invitación y Pase QR</h3>
            <p className="sub-card">Crea un pase rápido con código QR para enviar por WhatsApp a tu invitado o delivery.</p>
            <form onSubmit={generarVisita} className="form-visita-rapida">
              <div className="form-grid-dos">
                <label>
                  Nombre de la visita:
                  <input
                    type="text"
                    required
                    placeholder="Ej: Juan Pérez"
                    value={visitaForm.nombre}
                    onChange={(e) => setVisitaForm({ ...visitaForm, nombre: e.target.value })}
                  />
                </label>
                <label>
                  RUT (opcional):
                  <input
                    type="text"
                    placeholder="12.345.678-9"
                    value={visitaForm.rut}
                    onChange={(e) => setVisitaForm({ ...visitaForm, rut: e.target.value })}
                  />
                </label>
              </div>
              <label>
                Patente del vehículo (si ingresa en auto al portón):
                <input
                  type="text"
                  placeholder="Ej: BBCD12"
                  value={visitaForm.patente}
                  onChange={(e) => setVisitaForm({ ...visitaForm, patente: e.target.value.toUpperCase() })}
                />
              </label>
              <button type="submit" className="btn-primario-grande">
                Generar Código QR de Acceso
              </button>
            </form>

            {visitaQr && (
              <div className="tarjeta-qr-generada">
                <div className="qr-simulado">
                  <div className="qr-box">
                    <span className="qr-text">{visitaQr.codigo}</span>
                  </div>
                </div>
                <div className="qr-datos">
                  <h4>{visitaQr.nombre}</h4>
                  <p>Válido para ingresar al Depto {unidad.numero}</p>
                  {visitaQr.patente && <Placa valor={visitaQr.patente} pequena />}
                  <button
                    type="button"
                    className="btn-whatsapp"
                    onClick={() => {
                      const msg = `¡Hola ${visitaQr.nombre}! Este es tu pase de acceso para visitarme en el Depto ${unidad.numero} de ${data.edificio.nombre}. Tu código de acceso es ${visitaQr.codigo}.`;
                      window.open(`https://api.whatsapp.com/send?text=${encodeURIComponent(msg)}`, "_blank");
                    }}
                  >
                    💬 Compartir por WhatsApp
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 3. SECCIÓN ENCOMIENDAS (CARACTERÍSTICA EDIFITO) */}
      {tabInterno === "encomiendas" && (
        <div className="portal-encomiendas-wrap">
          <div className="card-encomiendas">
            <div className="card-cabecera">
              <div>
                <h3>Paquetería y Encomiendas en Conserjería</h3>
                <p className="sub-card">Paquetes recibidos por conserjería para el Departamento {unidad.numero}.</p>
              </div>
              <span className="pill-al-dia">{encomiendas.filter((x) => x.estado === "pendiente").length} por retirar</span>
            </div>

            <ul className="lista-encomiendas">
              {encomiendas.map((enc) => (
                <li key={enc.id} className={`item-encomienda ${enc.estado}`}>
                  <div className="encomienda-icono">{enc.courier.toLowerCase().includes("mercado") ? "🟡" : "📦"}</div>
                  <div className="encomienda-info">
                    <b>{enc.courier}</b>
                    <span>{enc.detalle}</span>
                    <small>Recibido: {enc.recepcion}</small>
                  </div>
                  <div className="encomienda-estado">
                    {enc.estado === "pendiente" ? (
                      <button className="btn-retirar" onClick={() => marcarRetiroEncomienda(enc.id)}>
                        Confirmar Retiro
                      </button>
                    ) : (
                      <span className="estado-entregado">✓ Entregado</span>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {/* 4. SECCIÓN COMUNICADOS OFICIALES */}
      {tabInterno === "comunicados" && (
        <div className="portal-comunicados-wrap">
          <div className="card-comunicados">
            <h3>Muro de Comunicados Oficiales</h3>
            <p className="sub-card">Información y circulares emitidas por la administración de {data.edificio.nombre}.</p>
            <div className="lista-comunicados">
              {COMUNICADOS_EJEMPLO.map((c) => (
                <article key={c.id} className={`item-comunicado ${c.urgente ? "urgente" : ""}`}>
                  <div className="comunicado-header">
                    <span className="categoria-tag">{c.categoria}</span>
                    <time>{c.fecha}</time>
                  </div>
                  <h4>{c.titulo}</h4>
                  <p>{c.cuerpo}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 5. SECCIÓN VEHÍCULOS Y STICKERS */}
      {tabInterno === "vehiculos" && (
        <div className="portal-vehiculos-wrap">
          <div className="card-vehiculos">
            <h3>Vehículos y Tags Registrados</h3>
            <p className="sub-card">Estacionamientos asignados: {unidad.estacionamientos} · Autos registrados: {unidad.vehiculos.length}</p>

            {unidad.vehiculos.length === 0 ? (
              <p className="vacio">No hay vehículos registrados para este departamento.</p>
            ) : (
              <div className="grid-autos-propietario">
                {unidad.vehiculos.map((v) => (
                  <div key={v.id} className="tarjeta-auto">
                    <Placa valor={v.patente} />
                    <div className="auto-detalles">
                      <b>{v.descripcion || "Vehículo particular"}</b>
                      <span className="auto-tag-status">
                        {v.sticker ? "✓ Sticker UHF activo (apertura automática)" : "📷 Acceso por cámara de patente"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
