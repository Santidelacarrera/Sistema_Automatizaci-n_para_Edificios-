"""Expansión semántica, normalización léxica, sinónimos de dominio y resolución de correferencias."""
from difflib import get_close_matches
import re
import unicodedata

STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "con", "por",
    "para", "que", "como", "cual", "cuales", "quien", "quienes", "donde", "cuando", "cuanto", "cuanta",
    "cuantos", "y", "o", "u", "pero", "si", "no", "su", "sus", "mi", "mis", "tu", "tus", "es", "son",
    "esta", "estan", "hay", "tiene", "tienen", "sobre", "entre", "hasta", "desde", "sobre", "ese", "esa",
    "eso", "esto", "esta", "aqui", "alli", "se", "me", "te", "lo", "le", "les",
}

SINONIMOS_DOMINIO: dict[str, list[str]] = {
    "morosidad": ["deuda", "atraso", "atrasado", "impago", "vencido", "pendiente", "plata", "cuota", "debe"],
    "deuda": ["morosidad", "saldo", "cargo", "pendiente", "cobranza", "impago", "debe"],
    "gasto": ["gastos", "comun", "comunes", "cuota", "mensualidad", "prorrateo", "cobro"],
    "multa": ["sancion", "penalizacion", "infraccion", "castigo", "penalidad"],
    "reserva": ["reservar", "agendar", "apartar", "horario", "disponibilidad", "espacio", "quincho", "salon", "piscina"],
    "garantia": ["deposito", "resguardo", "fianza", "caucion"],
    "quincho": ["parrilla", "asado", "barbacoa", "espacio", "salon"],
    "visita": ["invitado", "visitante", "huesped", "ingreso", "pase", "qr", "recurrente"],
    "porteria": ["conserje", "conserjeria", "guardia", "recepcion", "entrada", "acceso"],
    "encomienda": ["paquete", "correspondencia", "delivery", "envio", "reparto", "caja"],
    "incidencia": ["falla", "averia", "problema", "reclamo", "reparacion", "arreglo", "mantencion", "mantenimiento"],
    "mantencion": ["mantenimiento", "revision", "preventivo", "tecnico", "reparacion", "orden"],
    "proveedor": ["contratista", "empresa", "servicio", "tecnico", "cotizacion"],
    "asamblea": ["reunion", "junta", "votacion", "quorum", "acta", "acuerdo", "comite"],
    "reglamento": ["norma", "normativa", "regla", "prohibicion", "horario", "mudanza", "mascota", "ruido"],
    "mudanza": ["traslado", "flete", "camion", "cambio"],
    "mascota": ["perro", "gato", "animal", "tenencia"],
    "ruido": ["molestia", "fiesta", "musica", "volumen", "decibeles", "descanso"],
    "estacionamiento": ["parking", "auto", "vehiculo", "patente", "cochera", "porton", "uhf"],
    "agua": ["consumo", "medidor", "filtracion", "gotera", "fuga", "gasfiteria"],
    "fondo": ["reserva", "ahorro", "emergencia", "respaldo"],
}

_INVERSO: dict[str, set[str]] = {}
for raiz, lista in SINONIMOS_DOMINIO.items():
    _INVERSO.setdefault(raiz, set()).update(lista)
    for item in lista:
        _INVERSO.setdefault(item, set()).add(raiz)
        _INVERSO[item].update(x for x in lista if x != item)


def normalizar_texto(texto: str) -> str:
    s = unicodedata.normalize("NFKD", (texto or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9\s]", " ", s)


def stem_ligero(tok: str) -> str:
    if len(tok) > 5 and tok.endswith(("ciones", "siones")):
        return tok[:-4]
    if len(tok) > 4 and tok.endswith(("es", "as", "os")):
        return tok[:-2]
    if len(tok) > 4 and tok.endswith("s"):
        return tok[:-1]
    return tok


def tokenizar(texto: str, incluir_stems: bool = True) -> list[str]:
    norm = normalizar_texto(texto)
    toks = [t for t in norm.split() if len(t) >= 2 and t not in STOPWORDS_ES]
    if not incluir_stems:
        return toks
    salida = list(toks)
    for t in toks:
        st = stem_ligero(t)
        if st != t:
            salida.append(st)
    return salida


def expandir_consulta(
    pregunta: str,
    vocabulario_indexado: set[str] | None = None,
    historial_sesion: list[str] | None = None,
    entidades_activas: list[str] | None = None,
) -> dict:
    """Genera variantes semánticas, corrige typos acotados y resuelve correferencias de sesión."""
    base_toks = tokenizar(pregunta, incluir_stems=False)
    resuelta = pregunta.strip()

    # 1. Resolución simple de correferencias usando entidades/turnos previos de la sesión
    marcadores_ref = ("ese", "esa", "eso", "mismo", "misma", "anterior", "lo mismo", "depto", "ahi", "alli")
    if (historial_sesion or entidades_activas) and any(m in normalizar_texto(pregunta).split() for m in marcadores_ref):
        extra_ctx = " ".join((entidades_activas or [])[-2:] or (historial_sesion or [])[-2:])
        if extra_ctx:
            resuelta = f"{resuelta} ({extra_ctx[:140]})"

    expandidos: list[str] = list(tokenizar(resuelta))
    sinonimos_usados: list[str] = []

    # 2. Tolerancia a typos contra vocabulario indexado o diccionario de dominio
    vocab_total = set(_INVERSO.keys()) | (vocabulario_indexado or set())
    for t in base_toks:
        if len(t) >= 4 and t not in vocab_total:
            cercanos = get_close_matches(t, vocab_total, n=2, cutoff=0.78)
            for c in cercanos:
                if c not in expandidos:
                    expandidos.append(c)
                    sinonimos_usados.append(f"{t}~{c}")

    # 3. Expansión de sinónimos y jerga del dominio
    for t in list(expandidos):
        for syn in _INVERSO.get(t, ()):
            if syn not in expandidos:
                expandidos.append(syn)
                sinonimos_usados.append(f"{t}->{syn}")

    return {
        "pregunta_resuelta": resuelta,
        "tokens_base": tokenizar(resuelta),
        "tokens_expandidos": expandidos,
        "variantes": sinonimos_usados[:15],
    }
