// Cliente del backend + datos de demostración (modo demo: nada sale del navegador).
const BASE = process.env.NEXT_PUBLIC_API_URL || "";

export class ApiError extends Error {
  constructor(status, detail) { super(typeof detail === "string" ? detail : JSON.stringify(detail)); this.status = status; this.detail = detail; }
}

export const session = {
  get() { try { return JSON.parse(sessionStorage.getItem("sess") || "null"); } catch { return null; } },
  set(s) { try { sessionStorage.setItem("sess", JSON.stringify(s)); } catch {} },
  clear() { try { sessionStorage.removeItem("sess"); } catch {} },
};

async function http(sess, method, path, body) {
  const r = await fetch(BASE + path, {
    method,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${sess.token}` },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.detail ?? r.statusText);
  return data;
}

export async function login(edificio_id, email, password) {
  const r = await fetch(BASE + "/auth/login", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ edificio_id, email, password }),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, data.detail ?? "No se pudo iniciar sesión");
  return { token: data.access_token, edificio_id, demo: false, rol: data.rol, nombre: data.nombre };
}

export const apiHasBackend = () => Boolean(BASE);

// Sólo superadmin: resumen de todos los edificios.
export const listarEdificios = (sess) => http(sess, "GET", "/edificios");

// ---------- cliente unificado (real o demo) ----------
export function client(sess) {
  if (sess.demo) return demoClient();
  const e = `/edificios/${sess.edificio_id}`;
  return {
    panel: () => http(sess, "GET", `${e}/panel`),
    accesos: () => http(sess, "GET", `${e}/accesos?limit=60`),
    visitas: () => http(sess, "GET", `${e}/visitas`),
    cobranza: () => http(sess, "GET", `${e}/cobranza`),
    addVehiculo: (b) => http(sess, "POST", `${e}/vehiculos`, b),
    delVehiculo: (id) => http(sess, "DELETE", `${e}/vehiculos/${id}`),
    recordatorios: (b) => http(sess, "POST", `${e}/cobranza/recordatorios`, b),
    ...adminClient((m, p, b) => http(sess, m, `${e}${p}`, b)),
    // La cartola va como multipart: el navegador fija el borde del formulario, por eso sin Content-Type.
    conciliar: async (archivo) => {
      const fd = new FormData(); fd.append("cartola", archivo);
      const r = await fetch(`${BASE}${e}/conciliacion`, { method: "POST", headers: { Authorization: `Bearer ${sess.token}` }, body: fd });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) throw new ApiError(r.status, data.detail ?? r.statusText);
      return data;
    },
    // El QR exige sesión: se baja con el token y se muestra como imagen local (nunca en una URL pública).
    qrVisita: async (id) => {
      const r = await fetch(`${BASE}${e}/visitas/${id}/qr.png`, { headers: { Authorization: `Bearer ${sess.token}` } });
      if (!r.ok) throw new ApiError(r.status, "No se pudo cargar el QR");
      return URL.createObjectURL(await r.blob());
    },
    ...comunidadClient((m, p, b) => http(sess, m, `${e}${p}`, b)),
  };
}

// Comunidad: Mi Depto, comunicados, encomiendas, avisos de pago e intereses.
function comunidadClient(req) {
  return {
    miDepto: (unidad_id) => req("GET", `/mi-depto${unidad_id ? `?unidad_id=${unidad_id}` : ""}`),
    comunicados: () => req("GET", "/comunicados?todos=true"),
    publicarComunicado: (b) => req("POST", "/comunicados", b),
    retirarComunicado: (id) => req("DELETE", `/comunicados/${id}`),
    encomiendas: (estado) => req("GET", `/encomiendas${estado ? `?estado=${estado}` : ""}`),
    recibirEncomienda: (b) => req("POST", "/encomiendas", b),
    entregarEncomienda: (id, retirada_por) => req("POST", `/encomiendas/${id}/entregar`, { retirada_por }),
    avisosPago: () => req("GET", "/avisos-pago"),
    avisarPago: (b) => req("POST", "/avisos-pago", b),
    resolverAviso: (id, aprobar, motivo = "") => req("POST", `/avisos-pago/${id}/resolver`, { aprobar, motivo }),
    cobrarIntereses: (b) => req("POST", "/cobranza/intereses", b),
    resumenFinanzas: () => req("GET", "/finanzas/resumen"),
    espaciosComunes: () => req("GET", "/espacios-comunes"),
    disponibilidad: (id, fecha) => req("GET", `/espacios-comunes/${id}/disponibilidad?fecha=${fecha}`),
    reservarEspacio: (b) => req("POST", "/reservas-espacio", b),
    reservarVisita: (b) => req("POST", "/visitas", b),
    compartirVisita: (id, telefono = "") => req("GET", `/visitas/${id}/whatsapp?telefono=${encodeURIComponent(telefono)}`),
  };
}

// Administración (sólo admin): residentes, tags RFID y reglas del motor.
function adminClient(req) {
  return {
    residentes: () => req("GET", "/residentes"),
    crearResidente: (b) => req("POST", "/residentes", b),
    editarResidente: (id, b) => req("PATCH", `/residentes/${id}`, b),
    tags: () => req("GET", "/tags"),
    crearTag: (b) => req("POST", "/tags", b),
    editarTag: (id, b) => req("PATCH", `/tags/${id}`, b),
    espacios: () => req("GET", "/espacios"),
    reglas: () => req("GET", "/reglas"),
    crearRegla: (b) => req("POST", "/reglas", b),
    editarRegla: (id, b) => req("PATCH", `/reglas/${id}`, b),
    activarTag: (id) => req("POST", `/tags/${id}/activar`),
    perderTag: (id, motivo) => req("POST", `/tags/${id}/perder`, { motivo }),
    bloquearTag: (id, motivo) => req("POST", `/tags/${id}/bloquear`, { motivo }),
    reasignarTag: (id, b) => req("POST", `/tags/${id}/reasignar`, b),
    vincularTag: (id, vehiculo_id) => req("POST", `/tags/${id}/vincular`, { vehiculo_id }),
    desvincularTag: (id) => req("POST", `/tags/${id}/desvincular`),
    ajustesAcceso: () => req("GET", "/ajustes-acceso"),
    guardarAjustes: (b) => req("PATCH", "/ajustes-acceso", b),
    rotarClaveLectores: () => req("POST", "/dispositivos/rotar-clave"),
    pruebasAlcance: () => req("GET", "/pruebas-alcance"),
    anotarPruebaAlcance: (b) => req("POST", "/pruebas-alcance", b),
    reservarVisita: (b) => req("POST", "/visitas", b),
    reservasEspacio: () => req("GET", "/reservas-espacio"),
    reservarEspacio: (b) => req("POST", "/reservas-espacio", b),
    cancelarReserva: (id) => req("POST", `/reservas-espacio/${id}/cancelar`),
    periodosGastos: () => req("GET", "/gastos-comunes"),
    generarGastos: (b) => req("POST", "/gastos-comunes/generar", b),
    enviarGastos: (periodo) => req("POST", `/gastos-comunes/enviar/${periodo}`),
    enviarCircular: (b) => req("POST", "/circulares", b),
    cargarLectura: (b) => req("POST", "/lecturas", b),
  };
}

// ---------- demo ----------
const NOMBRES = ["Ana Pérez", "Beto Soto", "Carla Muñoz", "Diego Rojas", "Elena Vidal", "Fabián Lagos", "Gloria Paz", "Hugo Reyes", "Irene Cortés", "Javier Silva"];
const AUTOS = ["Mazda 3 gris", "Kia Morning rojo", "Suzuki Swift azul", "Toyota Yaris blanco", "Hyundai Tucson negro", "Chevrolet Sail plata"];
const LETRAS = "BCDFGHJKLPRSTVWXYZ";
function patente(n) { // formato chileno actual: 4 letras + 2 números
  let s = ""; let x = n * 7919 + 13;
  for (let i = 0; i < 4; i++) { s += LETRAS[x % LETRAS.length]; x = Math.floor(x / 3) + 17 * (i + 1); }
  return s + String(10 + ((n * 37) % 90));
}

function demoData() {
  const unidades = []; let k = 0;
  for (let piso = 1; piso <= 9; piso++) for (let d = 1; d <= 4; d++) {
    k++;
    const numero = `${piso}${String(d).padStart(2, "0")}`;
    const est = k % 5 === 0 ? 0 : k % 3 === 0 ? 2 : 1;
    const vencida = k % 7 === 0 ? 118000 + (k % 4) * 21000 : 0;
    const deuda = vencida || (k % 11 === 0 ? 96000 : 0);
    const vehiculos = Array.from({ length: Math.min(est, k % 4 === 0 ? 1 : est) }, (_, i) => ({
      id: k * 10 + i, patente: patente(k * 3 + i), descripcion: AUTOS[(k + i) % AUTOS.length], sticker: (k + i) % 2 === 0 }));
    unidades.push({
      id: k, numero, estacionamientos: est, codigo_cobro: `CC-A-${numero}`, deuda, vencida,
      residentes: k % 13 === 0 ? [] : [{ id: k, nombre: NOMBRES[k % NOMBRES.length], telefono: "5691" + String(1000000 + k * 7331).slice(0, 7), email: `depto${numero}@correo.cl` }],
      vehiculos, visitas_activas: k % 9 === 0 ? 1 : 0,
    });
  }
  return { edificio: { id: "edificio_a", nombre: "Edificio Alameda 1450", cupos_visitas: 6, cupos_ocupados: 2 }, unidades };
}

function demoClient() {
  let data = demoData();
  const ahora = Date.now();
  const iso = (m) => new Date(ahora + m * 60000).toISOString();
  const accesos = Array.from({ length: 24 }, (_, i) => {
    const veh = data.unidades.flatMap((u) => u.vehiculos);
    const ok = i % 6 !== 4;
    const esSticker = i % 3 === 0;
    return { id: 100 - i, token: ok ? (esSticker ? "E280117000000000000000A1" : veh[i % veh.length].patente) : patente(900 + i),
      punto: i % 4 === 3 ? "peatonal" : "vehicular", fuente: ok ? (esSticker ? "sticker" : "patente") : (i % 2 ? "patente" : "sticker"),
      permitido: ok,
      motivo: ok ? (esSticker ? "Residente" : "Patente de residente") : (i % 2 ? "Patente no registrada en este edificio" : "Sticker perdido: no abre"),
      creado: iso(-i * 7 - 1) };
  });
  const visitas = [
    { id: 1, unidad: "309", nombre: "Marcela Torres", patente: "KLPR45", desde: iso(-50), hasta: iso(70), estado: "llego", usa_estacionamiento: true },
    { id: 2, unidad: "703", nombre: "Gasfitería Rojas", patente: "TRSB21", desde: iso(-32), hasta: iso(20), estado: "llego", usa_estacionamiento: true },
    { id: 3, unidad: "204", nombre: "Pedro Aránguiz", patente: "", desde: iso(25), hasta: iso(160), estado: "reservada", usa_estacionamiento: false },
    { id: 4, unidad: "406", nombre: "Lucía y Tomás", patente: "WDZX88", desde: iso(95), hasta: iso(300), estado: "reservada", usa_estacionamiento: true },
    { id: 5, unidad: "101", nombre: "Delivery farmacia", patente: "", desde: iso(-70), hasta: iso(-20), estado: "no_show", usa_estacionamiento: false },
  ];
  const wait = (v) => new Promise((r) => setTimeout(() => r(structuredClone(v)), 120));
  const cob = () => {
    const m = data.unidades.filter((u) => u.deuda > 0).map((u) => ({ unidad_id: u.id, numero: u.numero, codigo_cobro: u.codigo_cobro,
      deuda: u.deuda, vencido: u.vencida, dias_atraso: u.vencida ? 20 + (u.id * 13) % 90 : 0 }));
    m.sort((a, b) => b.dias_atraso - a.dias_atraso);
    return { morosos: m, total: m.reduce((s, x) => s + x.deuda, 0) };
  };
  // Administración en memoria: mismas reglas de validación que el backend, sólo en el navegador.
  const u0 = data.unidades;
  const unidadNum = (id) => u0.find((x) => x.id === id)?.numero ?? "";
  let residentes = [
    { id: 1, nombre: "Ana Pérez", rut: "12.345.678-5", email: "ana@x.cl", telefono: "56911112222", unidad_id: u0[0].id, rol: "admin", activo: true },
    { id: 2, nombre: "Beto Soto", rut: "11.111.111-1", email: "beto@x.cl", telefono: "56933334444", unidad_id: u0[1].id, rol: "residente", activo: true },
  ].map((r) => ({ ...r, unidad: unidadNum(r.unidad_id) }));
  const epcDemo = (k) => `E280117000000000${String(k).padStart(8, "0")}`;
  let tags = [
    { id: 1, uid: "E280117000000000000000A1", formato: "epc", tipo: "vehicular", estado: "activo", unidad_id: u0[0].id, residente_id: 1, patente: "BBCD12", fecha_alta: iso(-9000), ultima_lectura: iso(-40) },
    { id: 2, uid: epcDemo(2), formato: "epc", tipo: "vehicular", estado: "perdido", unidad_id: u0[1].id, residente_id: 2, patente: "", fecha_alta: iso(-8000), ultima_lectura: iso(-900) },
    { id: 3, uid: epcDemo(3), formato: "epc", tipo: "vehicular", estado: "activo", unidad_id: u0[2].id, residente_id: null, patente: "", fecha_alta: iso(-7000), ultima_lectura: null },
    { id: 4, uid: "W26:42:12345", formato: "wiegand", tipo: "vehicular", estado: "bloqueado", unidad_id: u0[3].id, residente_id: null, patente: "CDFG34", fecha_alta: iso(-6000), ultima_lectura: null },
  ];
  let ajustes = { modo_acceso: "sticker_o_patente", ventana_coincidencia_s: 10, antirrebote_s: 3, anti_passback: false, umbral_confianza_patente: 0.85 };
  let pruebas = [];
  let espacios = [{ id: 1, nombre: "Quincho", accion: "reservar_quincho", tarifa: 10000 }];
  let reglas = [{ id: 1, accion: "reservar_quincho", tipo: "horario", params: { desde: "10:00", hasta: "22:00" }, activa: true }];
  const nid = (lista) => Math.max(0, ...lista.map((x) => x.id)) + 1;
  const fallo = (msg, status = 422) => { throw new ApiError(status, msg); };
  const tagDemo = (id) => { const t = tags.find((x) => x.id === id); if (!t) fallo("Tag no existe", 404); return t; };
  let reservas = [];
  let periodos = [];
  const admin = {
    reservarVisita: async (b) => {
      const ocupados = visitas.filter((v) => v.usa_estacionamiento && v.estado !== "no_show" && new Date(v.desde) < new Date(b.hasta) && new Date(v.hasta) > new Date(b.desde)).length;
      if (b.usa_estacionamiento && ocupados >= 6) fallo("Sin cupos de estacionamiento de visitas en ese horario", 409);
      const u = data.unidades.find((x) => x.id === b.unidad_id) || fallo("Unidad no existe en este edificio", 404);
      const v = { id: nid(visitas), unidad: u.numero, nombre: b.nombre_visita, patente: (b.patente || "").toUpperCase().replace(/[^A-Z0-9]/g, ""),
        desde: b.desde, hasta: b.hasta, estado: "reservada", usa_estacionamiento: b.usa_estacionamiento };
      visitas.push(v); return { id: v.id, codigo_qr: "demo-" + v.id };
    },
    reservasEspacio: async () => reservas.map((r) => ({ ...r })),
    reservarEspacio: async (b) => {
      const esp = espacios.find((x) => x.id === b.espacio_id) || fallo("Espacio no existe", 404);
      if (new Date(b.hasta) <= new Date(b.desde)) fallo("Rango horario inválido");
      if (reservas.some((r) => r.espacio === esp.nombre && r.estado === "confirmada" && new Date(r.desde) < new Date(b.hasta) && new Date(r.hasta) > new Date(b.desde))) fallo("Espacio ya reservado en ese horario", 409);
      const h = (d) => { const x = new Date(d); return x.getHours() * 60 + x.getMinutes(); };
      if (h(b.desde) < 600 || h(b.hasta) > 1320) fallo({ motivos: ["Horario permitido: 10:00–22:00"] });
      const u = data.unidades.find((x) => x.id === b.unidad_id);
      const r = { id: nid(reservas), espacio: esp.nombre, unidad: u.numero, desde: b.desde, hasta: b.hasta, estado: "confirmada" };
      reservas.push(r); return { id: r.id, tarifa: esp.tarifa };
    },
    cancelarReserva: async (id) => {
      const r = reservas.find((x) => x.id === id) || fallo("Reserva no existe", 404);
      if (r.estado !== "confirmada") fallo("La reserva ya estaba cancelada", 409);
      const horas = (new Date(r.desde) - new Date()) / 3600000;
      r.estado = "cancelada"; return { estado: "cancelada", multa: horas < 24 ? 15000 : 0, tarifa_anulada: horas >= 24 };
    },
    periodosGastos: async () => periodos.map((p) => ({ ...p })),
    generarGastos: async (b) => {
      if (periodos.some((p) => p.periodo === b.periodo)) fallo(`Ya se generaron gastos comunes para ${b.periodo}`);
      const total = b.gastos.reduce((s, g) => s + Number(g.monto), 0);
      periodos.unshift({ periodo: b.periodo, emitido: total, pendiente: total, unidades: data.unidades.length });
      return { periodo: b.periodo, total, unidades: data.unidades.length };
    },
    enviarGastos: async () => ({ encolado: false, estado: "no_configurado", motivo: "Modo ejemplo: no se envía ningún correo." }),
    enviarCircular: async () => ({ encolado: false, estado: "no_configurado", motivo: "Modo ejemplo: no se envía ningún correo." }),
    cargarLectura: async () => ({ ok: true }),
    conciliar: async (archivo) => {
      const texto = await archivo.text();
      const filas = texto.trim().split("\n").slice(1).filter(Boolean);
      return { conciliados: filas.slice(0, 1).map((f, i) => ({ id: "demo" + i, unidad: "101", monto: 50000, excedente: 0 })),
        sin_match: filas.slice(1).map((f, i) => ({ id: "demo-s" + i, descripcion: f.split(",")[1] || "", monto: Number(f.split(",")[2]) || 0 })), duplicados: 0, demo: true };
    },
    qrVisita: async () => "data:image/svg+xml;utf8," + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="160" height="160"><rect width="160" height="160" fill="#fff"/><rect x="12" y="12" width="44" height="44" fill="#1b2336"/><rect x="104" y="12" width="44" height="44" fill="#1b2336"/><rect x="12" y="104" width="44" height="44" fill="#1b2336"/><rect x="70" y="70" width="20" height="20" fill="#1b2336"/><rect x="104" y="104" width="44" height="12" fill="#1b2336"/></svg>'),
    residentes: async () => residentes.map((r) => ({ ...r, unidad: unidadNum(r.unidad_id) })),
    crearResidente: async (b) => {
      if (residentes.some((r) => r.rut.replace(/\D/g, "") === b.rut.replace(/\D/g, ""))) fallo("El RUT ya está registrado en este edificio", 409);
      const r = { id: nid(residentes), ...b, activo: true, rol: b.rol || "residente" };
      residentes.push(r); return { id: r.id };
    },
    editarResidente: async (id, b) => {
      const r = residentes.find((x) => x.id === id); if (!r) fallo("Residente no existe", 404);
      Object.assign(r, Object.fromEntries(Object.entries(b).filter(([, v]) => v !== null && v !== undefined)));
      return { id };
    },
    tags: async () => tags.map((t) => ({ ...t, activo: t.estado === "activo", unidad: unidadNum(t.unidad_id), residente: residentes.find((r) => r.id === t.residente_id)?.nombre ?? null })),
    activarTag: async (id) => { const t = tagDemo(id); t.estado = "activo"; return { id, estado: t.estado }; },
    perderTag: async (id) => { const t = tagDemo(id); t.estado = "perdido"; return { id, estado: t.estado }; },
    bloquearTag: async (id) => { const t = tagDemo(id); t.estado = "bloqueado"; return { id, estado: t.estado }; },
    reasignarTag: async (id, b) => { const t = tagDemo(id); t.unidad_id = b.unidad_id; t.residente_id = b.residente_id ?? null; t.patente = ""; return { id, unidad_id: t.unidad_id }; },
    vincularTag: async (id, vehiculo_id) => {
      const t = tagDemo(id);
      if (t.patente) fallo(`El sticker ya está asociado a la patente ${t.patente}: desvincúlalo primero`, 409);
      const veh = data.unidades.flatMap((u) => u.vehiculos).find((v) => v.id === vehiculo_id);
      if (!veh) fallo("Vehículo no existe en este edificio", 404);
      t.patente = veh.patente; return { id };
    },
    desvincularTag: async (id) => { tagDemo(id).patente = ""; return { id }; },
    rotarClaveLectores: async () => ({ device_key: "demo-" + Math.random().toString(36).slice(2, 14), aviso: "Clave de ejemplo: en modo demo no cambia nada." }),
    ajustesAcceso: async () => ({ ...ajustes }),
    guardarAjustes: async (b) => { ajustes = { ...ajustes, ...Object.fromEntries(Object.entries(b).filter(([, v]) => v !== null && v !== undefined)) }; return { ...ajustes }; },
    pruebasAlcance: async () => pruebas,
    anotarPruebaAlcance: async (b) => { pruebas = [{ id: nid(pruebas), creado: new Date().toISOString(), ...b }, ...pruebas]; return { id: pruebas[0].id }; },
    crearTag: async (b) => {
      if (!/^[0-9A-F]{8,20}$/.test(b.uid.toUpperCase())) fallo("UID inválido: entre 8 y 20 caracteres hexadecimales (0-9, A-F)");
      if (tags.some((t) => t.uid === b.uid.toUpperCase())) fallo("UID ya registrado", 409);
      const t = { id: nid(tags), uid: b.uid.toUpperCase(), tipo: b.tipo, activo: true, unidad_id: b.unidad_id, residente_id: b.residente_id ?? null };
      tags.push(t); return { id: t.id };
    },
    editarTag: async (id, b) => {
      const t = tags.find((x) => x.id === id); if (!t) fallo("Tag no existe", 404);
      if ("residente_id" in b) t.residente_id = b.residente_id;
      if (b.activo !== undefined && b.activo !== null) t.activo = b.activo;
      return { id, activo: t.activo };
    },
    espacios: async () => espacios,
    reglas: async () => reglas,
    crearRegla: async (b) => {
      if (!espacios.some((e) => e.accion === b.accion)) fallo(`No hay un espacio común con la acción '${b.accion}'`);
      if (reglas.some((r) => r.accion === b.accion && r.tipo === b.tipo)) fallo(`Ya existe una regla de tipo ${b.tipo} para '${b.accion}'; edítala en lugar de crear otra`);
      const r = { id: nid(reglas), activa: true, params: {}, ...b };
      reglas.push(r); return { id: r.id };
    },
    editarRegla: async (id, b) => {
      const r = reglas.find((x) => x.id === id); if (!r) fallo("Regla no existe", 404);
      if (b.params) r.params = b.params;
      if (b.activa !== undefined && b.activa !== null) r.activa = b.activa;
      return { id, activa: r.activa };
    },
  };

  // Comunidad en memoria (modo demo).
  const u1 = data.unidades[0];
  let comunicados = [
    { id: 1, titulo: "Mantención de ascensores", cuerpo: "El jueves entre 9:00 y 13:00 se revisará el ascensor norte.", categoria: "mantencion", fijado: true, publicado_at: iso(-3000), vigente_hasta: null },
    { id: 2, titulo: "Asamblea ordinaria", cuerpo: "Sábado 18:00 en la sala multiuso. Se votará el presupuesto.", categoria: "asamblea", fijado: false, publicado_at: iso(-9000), vigente_hasta: null },
  ];
  let encomiendas = [
    { id: 1, unidad_id: u1.id, unidad: u1.numero, transportista: "Chilexpress", remitente: "", descripcion: "Caja mediana", estado: "pendiente", recibida_at: iso(-200), entregada_at: null, retirada_por: "" },
    { id: 2, unidad_id: data.unidades[5].id, unidad: data.unidades[5].numero, transportista: "Mercado Libre", remitente: "", descripcion: "", estado: "pendiente", recibida_at: iso(-90), entregada_at: null, retirada_por: "" },
  ];
  let avisos = [{ id: 1, unidad_id: data.unidades[6].id, unidad: data.unidades[6].numero, monto: 96000, banco: "Banco Estado", nro_operacion: "OP-448812", fecha_transferencia: new Date().toISOString().slice(0, 10), estado: "pendiente", creado: iso(-60), motivo: "" }];
  const comunidad = {
    miDepto: async () => ({
      unidad: { id: u1.id, numero: u1.numero, codigo_cobro: u1.codigo_cobro, estacionamientos: u1.estacionamientos },
      cuenta: { estado: u1.vencida > 0 ? "moroso" : "al_dia", deuda: u1.deuda, vencida: u1.vencida,
        desglose: { cuota_base: Math.round(u1.deuda * 0.7), agua: Math.round(u1.deuda * 0.2), fondo_reserva: Math.round(u1.deuda * 0.1), intereses_multas: 0, otros: 0 }, cargos: [] },
      vehiculos: u1.vehiculos, tags: [], encomiendas_pendientes: encomiendas.filter((e) => e.unidad_id === u1.id && e.estado === "pendiente"),
      visitas_activas: [], avisos_pago: avisos.filter((a) => a.unidad_id === u1.id), comunicados: comunicados.slice(0, 5),
    }),
    comunicados: async () => [...comunicados].sort((a, b) => Number(b.fijado) - Number(a.fijado)),
    publicarComunicado: async (b) => { const c = { id: nid(comunicados), publicado_at: new Date().toISOString(), vigente_hasta: null, fijado: false, categoria: "aviso", ...b }; comunicados.push(c); return { id: c.id }; },
    retirarComunicado: async (id) => { comunicados = comunicados.filter((c) => c.id !== id); return { ok: true }; },
    encomiendas: async (estado) => encomiendas.filter((e) => !estado || e.estado === estado),
    recibirEncomienda: async (b) => {
      const u = data.unidades.find((x) => x.id === b.unidad_id); if (!u) fallo("Unidad no existe en este edificio", 404);
      const e = { id: nid(encomiendas), unidad: u.numero, estado: "pendiente", recibida_at: new Date().toISOString(), entregada_at: null, retirada_por: "", remitente: "", descripcion: "", transportista: "", ...b };
      encomiendas.unshift(e); u.encomiendas = (u.encomiendas || 0) + 1; return { id: e.id };
    },
    entregarEncomienda: async (id, retirada_por) => {
      const e = encomiendas.find((x) => x.id === id); if (!e) fallo("Encomienda no existe", 404);
      if (e.estado === "entregada") fallo("La encomienda ya fue entregada", 409);
      Object.assign(e, { estado: "entregada", entregada_at: new Date().toISOString(), retirada_por }); return { id, estado: e.estado, entregada_at: e.entregada_at };
    },
    avisosPago: async () => avisos,
    avisarPago: async (b) => {
      if (avisos.some((a) => a.banco === b.banco && a.nro_operacion === b.nro_operacion)) fallo("Ese número de operación ya fue informado para ese banco", 409);
      const a = { id: nid(avisos), unidad_id: u1.id, unidad: u1.numero, estado: "pendiente", creado: new Date().toISOString(), motivo: "", ...b }; avisos.unshift(a); return { id: a.id, estado: a.estado };
    },
    resolverAviso: async (id, aprobar, motivo) => {
      const a = avisos.find((x) => x.id === id); if (!a) fallo("Aviso no existe", 404);
      if (!aprobar && !motivo?.trim()) fallo("Indica el motivo del rechazo");
      a.estado = aprobar ? "aprobado" : "rechazado"; a.motivo = motivo || ""; return { id, estado: a.estado, excedente: 0 };
    },
    cobrarIntereses: async (b) => { const m = cob().morosos.filter((x) => x.dias_atraso > 0); return { periodo: b.periodo, unidades: m.length, ya_aplicados: 0, total: Math.round(m.reduce((s, x) => s + x.vencido, 0) * b.tasa_mensual_pct / 100) }; },
    resumenFinanzas: async () => { const c = cob(); const mor = c.morosos.filter((x) => x.dias_atraso > 0).length; return { unidades: data.unidades.length, unidades_morosas: mor, morosidad_pct: Math.round(mor / data.unidades.length * 1000) / 10, deuda_total: c.total, deuda_vencida: c.morosos.reduce((s, x) => s + x.vencido, 0), avisos_pago_pendientes: avisos.filter((a) => a.estado === "pendiente").length }; },
    espaciosComunes: async () => espacios.map((e) => ({ ...e, aforo: 20, horario: { desde: "10:00", hasta: "22:00" } })),
    disponibilidad: async () => ({ espacio: "Quincho", aforo: 20, tarifa: 10000, horario: { desde: "10:00", hasta: "22:00" }, abierto: true, ocupadas: [] }),
    reservarEspacio: async () => fallo("Modo demo: las reservas no se guardan"),
    reservarVisita: async () => fallo("Modo demo: las visitas no se guardan"),
    compartirVisita: async (id) => ({ mensaje: "Hola, te invito al depto 101. Muestra este código en la entrada: DEMO", url: "https://wa.me/?text=DEMO", codigo_qr: "DEMO" }),
  };
  return {
    ...admin, ...comunidad,
    panel: () => wait(data), accesos: () => wait(accesos), visitas: () => wait(visitas), cobranza: () => wait(cob()),
    addVehiculo: async (b) => {
      const u = data.unidades.find((x) => x.id === b.unidad_id);
      if (u.vehiculos.length >= u.estacionamientos) throw new ApiError(409, `La unidad ya tiene ${u.vehiculos.length} vehículo(s) (máx. ${u.estacionamientos})`);
      const pat = b.patente.toUpperCase().replace(/[^A-Z0-9]/g, "");
      if (pat.length < 5 || pat.length > 7) throw new ApiError(409, "Patente inválida");
      u.vehiculos.push({ id: Date.now(), patente: pat, descripcion: b.descripcion, sticker: false });
      return { id: 1, patente: pat };
    },
    delVehiculo: async (id) => { data.unidades.forEach((u) => { u.vehiculos = u.vehiculos.filter((v) => v.id !== id); }); return { ok: true }; },
    recordatorios: async (b) => {
      // Modo demo: no sale ningún mensaje; cada envío se muestra como no enviado, con su motivo.
      const sel = cob().morosos.filter((m) => !b.unidad_ids || b.unidad_ids.includes(m.unidad_id));
      const motivo = "Modo demo: el navegador no envía mensajes";
      const detalle = sel.flatMap((m) => b.canales.map((canal) => ({ unidad: m.numero, residente: "(demo)", canal, estado: "no_configurado", motivo })));
      return { unidades: sel.length, whatsapp: 0, email: 0, sin_contacto: sel.map((m) => m.numero), detalle, no_enviados: detalle.length, demo: true };
    },
  };
}

export const demoSession = () => ({ token: "demo", edificio_id: "edificio_a", demo: true });
export const clp = (n) => "$" + Math.round(n).toLocaleString("es-CL");
export const normPatente = (p) => (p || "").toUpperCase().replace(/[^A-Z0-9]/g, "");
