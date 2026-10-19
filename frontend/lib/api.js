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
  return { token: data.access_token, edificio_id, demo: false };
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
  return {
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
