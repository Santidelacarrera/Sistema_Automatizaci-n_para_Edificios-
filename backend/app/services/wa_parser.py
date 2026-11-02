"""Entiende mensajes en español de Chile para reservar una visita: nombre, día, hora, patente.

Reglas simples y predecibles (sin IA): lo que no se entiende se pregunta, no se adivina.
"""
import re
import unicodedata
from datetime import datetime, timedelta

DIAS = {"lunes": 0, "martes": 1, "miercoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "domingo": 6}
NOMBRE_DIA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

# Palabras que nunca forman parte del nombre de la visita.
_RUIDO = set("""quiero queria quisiera necesito reservar reserva reservame agendar agenda registrar registra visita visitas
invitado invitada para de del la el los las un una mi mis con en a al por que favor hola buenas buenos dias tardes noches
estacionamiento estacionar auto vehiculo vehiculos camioneta moto patente placa hoy manana pasado desde hasta las hrs hr
horas hora h am pm llega llegar llegara viene vendra va ira se ir y e o sin pie caminando hermano hermana amigo amiga mama papa primo prima tio tia suegro suegra""".split())

# Formatos chilenos: BBCD12 / BBCD-12 / BB-CD-12 (actual) y AB1234 / AB-1234 (antiguo). Sin espacios: así no se
# confunde "Soto 15" (apellido y día) con una patente.
RE_PATENTE = re.compile(r"\b([A-Za-z]{2}-[A-Za-z]{2}-\d{2}|[A-Za-z]{4}-?\d{2}|[A-Za-z]{2}-?\d{4})\b(?!/)")
RE_HORA = re.compile(r"\b(\d{1,2})\s*(?:[:h.]\s*(\d{2}))?\s*(am|pm|hrs?|h)?\b", re.I)


def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _hora(txt: str):
    """Devuelve (hora, minuto) o None. Acepta 18:00, 18h, 6pm, 'a las 6' (se asume tarde si es de 1 a 7)."""
    m = re.search(r"\b(\d{1,2})\s*[:h.]\s*(\d{2})\b", txt) or re.search(r"\b(\d{1,2})\s*(am|pm)\b", txt) \
        or re.search(r"\ba las\s+(\d{1,2})\b", txt) or re.search(r"\b(\d{1,2})\s*(?:hrs?|h)\b", txt)
    if not m:
        return None
    h = int(m.group(1))
    minuto = int(m.group(2)) if m.lastindex and m.lastindex >= 2 and (m.group(2) or "").isdigit() else 0
    sufijo = (m.group(2) or "").lower() if m.lastindex and m.lastindex >= 2 else ""
    if sufijo == "pm" and h < 12:
        h += 12
    elif sufijo == "am" and h == 12:
        h = 0
    elif not sufijo and "a las" in m.group(0) and 1 <= h <= 7:
        h += 12  # "a las 6" en una visita casi siempre es de tarde
    if not (0 <= h <= 23 and 0 <= minuto <= 59):
        return None
    return h, minuto


def _fecha(txt: str, ahora: datetime):
    if "pasado manana" in txt:
        return (ahora + timedelta(days=2)).date()
    if "manana" in txt:
        return (ahora + timedelta(days=1)).date()
    if re.search(r"\bhoy\b", txt):
        return ahora.date()
    for nombre, idx in DIAS.items():
        if re.search(rf"\b{nombre}\b", txt):
            delta = (idx - ahora.weekday()) % 7
            return (ahora + timedelta(days=delta or 7)).date()
    m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", txt)
    if m:
        d, mes = int(m.group(1)), int(m.group(2))
        anio = int(m.group(3)) if m.group(3) else ahora.year
        anio += 2000 if anio < 100 else 0
        try:
            f = datetime(anio, mes, d).date()
        except ValueError:
            return None
        if not m.group(3) and f < ahora.date():
            f = f.replace(year=f.year + 1)
        return f
    return None


def extraer_visita(texto: str, ahora: datetime) -> dict:
    """Campos que se lograron entender; el resto no aparece en el resultado."""
    out: dict = {}
    pat = RE_PATENTE.search(texto)
    if pat:
        out["patente"] = pat.group(1).replace("-", "").upper()
    plano = _plano(texto)
    sin_pat = _plano(texto.replace(pat.group(0), " ")) if pat else plano
    if re.search(r"\b(a pie|caminando|sin auto|sin estacionamiento|no usa estacionamiento)\b", plano):
        out["usa_estacionamiento"] = False
    elif pat or re.search(r"\b(auto|vehiculo|camioneta|estacionamiento|moto)\b", plano):
        out["usa_estacionamiento"] = True
    h = _hora(sin_pat)
    f = _fecha(sin_pat, ahora)
    if f:
        out["fecha"] = f.isoformat()
    if h:
        out["hora"] = f"{h[0]:02d}:{h[1]:02d}"
    dur = re.search(r"\bpor\s+(\d{1,2})\s*(?:horas?|hrs?)\b", sin_pat)
    if dur and 1 <= int(dur.group(1)) <= 12:
        out["duracion_h"] = int(dur.group(1))
    # Nombre: lo que queda de las palabras originales (con tildes y mayúsculas) tras quitar ruido, fechas y horas.
    sobrantes = []
    texto_sin = texto.replace(pat.group(0), " ") if pat else texto
    for palabra in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ'’-]+", texto_sin):
        p = _plano(palabra)
        if p in _RUIDO or p in DIAS or len(p) < 2:
            continue
        sobrantes.append(palabra)
    if sobrantes:
        out["nombre"] = " ".join(w.capitalize() if w.islower() else w for w in sobrantes)[:80]
    return out


def a_horario(datos: dict):
    """(desde, hasta) como datetimes locales, o None si falta la fecha o la hora."""
    if "fecha" not in datos or "hora" not in datos:
        return None
    desde = datetime.fromisoformat(f"{datos['fecha']}T{datos['hora']}")
    return desde, desde + timedelta(hours=int(datos.get("duracion_h", 3)))


def describir_dia(f: datetime) -> str:
    return f"{NOMBRE_DIA[f.weekday()]} {f.strftime('%d/%m')} a las {f.strftime('%H:%M')}"
