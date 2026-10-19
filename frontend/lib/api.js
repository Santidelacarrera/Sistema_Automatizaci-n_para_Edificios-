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
    return { id: 100 - i, token: ok ? (i % 3 === 0 ? "04A1B2C3" : veh[i % veh.length].patente) : patente(900 + i),
      punto: i % 4 === 3 ? "peatonal" : "vehicular", permitido: ok,
      motivo: ok ? (i % 3 === 0 ? "Residente" : "Patente de residente") : "Credencial desconocida", creado: iso(-i * 7 - 1) };
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
  let tags = [{ id: 1, uid: "04A1B2C3", tipo: "vehicular", activo: true, unidad_id: u0[0].id, residente_id: 1 }];
  let espacios = [{ id: 1, nombre: "Quincho", accion: "reservar_quincho", tarifa: 10000 }];
  let reglas = [{ id: 1, accion: "reservar_quincho", tipo: "horario", params: { desde: "10:00", hasta: "22:00" }, activa: true }];
  const nid = (lista) => Math.max(0, ...lista.map((x) => x.id)) + 1;
  const fallo = (msg, status = 422) => { throw new ApiError(status, msg); };
  const admin = {
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
    tags: async () => tags.map((t) => ({ ...t, unidad: unidadNum(t.unidad_id), residente: residentes.find((r) => r.id === t.residente_id)?.nombre ?? null })),
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
  return {
    ...admin,
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
