"""Chunking consciente de estructura: respeta encabezados, tablas, listas y bloques."""
from dataclasses import dataclass
import re


@dataclass
class ChunkEstructural:
    orden: int
    seccion: str
    tipo_bloque: str  # texto | tabla | lista
    contenido: str
    metadatos: dict


_RE_ENCABEZADO = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
_RE_SECCION_NUM = re.compile(r"^(?:ART[IÍ]CULO|SECCI[ÓO]N|CAP[IÍ]TULO)\s+[0-9A-Z]+[:.\-\s]+(.+)$", re.IGNORECASE)


def chunkear_documento(texto: str, titulo: str = "", max_chars: int = 750, overlap_chars: int = 120) -> list[ChunkEstructural]:
    """Divide texto estructurado preservando secciones completas, tablas y listas sin cortar a mitad."""
    lineas = (texto or "").replace("\r\n", "\n").split("\n")
    bloques: list[tuple[str, str, str]] = []  # (seccion, tipo_bloque, contenido)
    seccion_actual = titulo.strip() or "General"
    buffer: list[str] = []
    tipo_actual = "texto"

    def vaciar():
        nonlocal buffer, tipo_actual
        cuerpo = "\n".join(buffer).strip()
        if cuerpo:
            bloques.append((seccion_actual, tipo_actual, cuerpo))
        buffer = []
        tipo_actual = "texto"

    for linea in lineas:
        s = linea.strip()
        m_h = _RE_ENCABEZADO.match(s)
        m_sec = _RE_SECCION_NUM.match(s)
        if m_h:
            vaciar()
            seccion_actual = m_h.group(2).strip()[:180]
            continue
        if m_sec and len(s) <= 120:
            vaciar()
            seccion_actual = s[:180]
            continue
        if not s:
            vaciar()
            continue
        es_tabla = s.startswith("|") and "|" in s[1:]
        es_lista = s.startswith(("- ", "* ", "• ")) or bool(re.match(r"^\d+[.)]\s+", s))
        nuevo_tipo = "tabla" if es_tabla else ("lista" if es_lista else "texto")
        if buffer and nuevo_tipo != tipo_actual:
            vaciar()
        tipo_actual = nuevo_tipo
        buffer.append(s)
    vaciar()

    if not bloques and (texto or "").strip():
        bloques.append((seccion_actual, "texto", texto.strip()))

    chunks: list[ChunkEstructural] = []
    orden = 0
    for seccion, tipo, contenido in bloques:
        if len(contenido) <= max_chars or tipo == "tabla":
            chunks.append(ChunkEstructural(
                orden=orden,
                seccion=seccion,
                tipo_bloque=tipo,
                contenido=f"[{seccion}] {contenido}" if seccion and seccion != "General" else contenido,
                metadatos={"seccion": seccion, "tipo_bloque": tipo, "titulo": titulo},
            ))
            orden += 1
            continue
        inicio = 0
        while inicio < len(contenido):
            fin = min(len(contenido), inicio + max_chars)
            if fin < len(contenido):
                corte = contenido.rfind(" ", inicio, fin)
                if corte > inicio + 100:
                    fin = corte
            trozo = contenido[inicio:fin].strip()
            if trozo:
                chunks.append(ChunkEstructural(
                    orden=orden,
                    seccion=seccion,
                    tipo_bloque=tipo,
                    contenido=f"[{seccion}] {trozo}" if seccion and seccion != "General" else trozo,
                    metadatos={"seccion": seccion, "tipo_bloque": tipo, "titulo": titulo},
                ))
                orden += 1
            if fin >= len(contenido):
                break
            inicio = max(0, fin - overlap_chars)
    return chunks
