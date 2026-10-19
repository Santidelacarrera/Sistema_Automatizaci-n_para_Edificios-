// Validaciones de formularios del panel. Espejo de backend/app/validacion.py y rules.py: el backend
// siempre decide; aquí sólo se corrige antes de enviar para mostrar el error junto al campo.

export function rutValido(rut) {
  const limpio = (rut || "").replace(/[.\-\s]/g, "").toUpperCase();
  if (!/^\d{7,8}[\dK]$/.test(limpio)) return false;
  const cuerpo = limpio.slice(0, -1), dv = limpio.slice(-1);
  let suma = 0, factor = 2;
  for (const d of [...cuerpo].reverse()) { suma += Number(d) * factor; factor = factor === 7 ? 2 : factor + 1; }
  const resto = 11 - (suma % 11);
  const esperado = resto === 11 ? "0" : resto === 10 ? "K" : String(resto);
  return dv === esperado;
}

export const emailValido = (e) => !e || (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e) && e.length <= 160);
export const telefonoValido = (t) => !t || (t.replace(/\D/g, "").length >= 8 && t.replace(/\D/g, "").length <= 15);
export const horaValida = (h) => /^([01]\d|2[0-3]):[0-5]\d$/.test(h || "");

// Errores de un formulario de residente: objeto campo -> mensaje (vacío = válido).
export function erroresResidente(f) {
  const e = {};
  if (!f.nombre?.trim()) e.nombre = "Escribe el nombre del residente.";
  if (!rutValido(f.rut)) e.rut = "RUT inválido: revisa el dígito verificador (ej. 12.345.678-5).";
  if (!emailValido(f.email)) e.email = "El correo no tiene un formato válido.";
  if (!telefonoValido(f.telefono)) e.telefono = "Teléfono: entre 8 y 15 dígitos (con +56 si es de Chile).";
  if (!f.unidad_id) e.unidad_id = "Elige el departamento.";
  return e;
}

export function erroresRegla(f) {
  const e = {};
  const p = f.params || {};
  if (f.tipo === "horario") {
    if (!horaValida(p.desde) || !horaValida(p.hasta)) e.hasta = "Las horas deben ser HH:MM.";
    else if (p.desde >= p.hasta) e.hasta = "La hora de término debe ser posterior a la de inicio (sin cruzar medianoche).";
  } else if (f.tipo === "max_por_mes") {
    if (!Number.isInteger(Number(p.max)) || Number(p.max) < 1 || Number(p.max) > 31) e.max = "Indica un número entre 1 y 31.";
  } else if (f.tipo === "bloquear_morosos") {
    if (p.deuda_max !== undefined && (Number(p.deuda_max) < 0 || Number.isNaN(Number(p.deuda_max)))) e.deuda_max = "La deuda máxima no puede ser negativa.";
  } else if (f.tipo === "anticipacion") {
    if (p.min_horas === undefined && p.max_dias === undefined) e.min_horas = "Indica al menos un mínimo de horas o un máximo de días.";
    if (p.max_dias !== undefined && (Number(p.max_dias) < 1 || Number(p.max_dias) > 365)) e.max_dias = "Entre 1 y 365 días.";
    if (p.min_horas !== undefined && Number(p.min_horas) < 0) e.min_horas = "No puede ser negativo.";
  }
  return e;
}

// Convierte un error 422 de FastAPI (lista de {loc, msg}) o un detail de texto en un mensaje legible.
export function mensajeError(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((d) => `${d.loc?.at(-1) ?? "dato"}: ${String(d.msg).replace(/^Value error, /, "")}`).join("; ");
  return "No se pudo guardar. Inténtalo de nuevo.";
}
