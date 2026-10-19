"""Importación masiva de stickers UHF desde CSV: idempotente, con rechazo de duplicados y reporte por línea.

Columnas (cabecera obligatoria, orden libre; separador ',' o ';'; UTF-8 con o sin BOM):
  epc           obligatoria. EPC hexadecimal (12-24) o código Wiegand W26:<fac>:<card> / W34:<fac>:<card>.
  depto         obligatoria. Número de departamento del edificio.
  patente       opcional. Si viene, se asocia el sticker a ese vehículo del departamento.
  rut_residente opcional. Residente del departamento que usa el sticker.

Reglas:
  - Un código repetido dentro del lote rechaza TODAS sus apariciones (no se sabe cuál es el bueno).
  - Un código ya registrado en el departamento se considera sin cambios (reimportar no duplica).
  - Un código ya registrado en otro departamento o edificio se rechaza.
"""
import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import validacion
from ..models import Edificio, Residente, Tag, TipoTag, Unidad, Vehiculo
from . import access
from .credenciales import CredencialInvalida, detectar_formato, normalizar

COLUMNAS_OBLIGATORIAS = ("epc", "depto")


@dataclass
class ReporteStickers:
    creados: int = 0
    sin_cambios: int = 0
    vinculados_patente: int = 0
    errores: list[tuple[int, str]] = field(default_factory=list)


def _separador(texto: str) -> str:
    primera = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primera.count(";") > primera.count(",") else ","


def importar(db: Session, edificio: Edificio, texto: str, dry_run: bool = False) -> ReporteStickers:
    rep = ReporteStickers()
    texto = texto.lstrip("﻿")
    lector = csv.DictReader(io.StringIO(texto), delimiter=_separador(texto))
    cabeceras = [(c or "").strip().lower() for c in (lector.fieldnames or [])]
    faltan = [c for c in COLUMNAS_OBLIGATORIAS if c not in cabeceras]
    if faltan:
        rep.errores.append((1, f"Faltan columnas: {', '.join(faltan)}"))
        return rep

    filas = []
    for f in lector:
        fila = {(k or "").strip().lower(): (v or "").strip() for k, v in f.items()}
        if any(fila.values()):
            filas.append((lector.line_num, fila))

    # 1) normalizar y detectar repetidos dentro del lote
    canonicos: dict[str, list[int]] = {}
    normalizadas: dict[int, str] = {}
    for linea, fila in filas:
        try:
            formato = detectar_formato(fila["epc"])
            if formato not in ("epc", "wiegand"):
                raise CredencialInvalida("EPC inválido: 12 a 24 caracteres hexadecimales o Wiegand W26/W34")
            canon = normalizar(fila["epc"], formato)
        except CredencialInvalida as e:
            rep.errores.append((linea, str(e)))
            continue
        normalizadas[linea] = canon
        canonicos.setdefault(canon, []).append(linea)
    for canon, lineas in canonicos.items():
        if len(lineas) > 1:
            for linea in lineas:
                rep.errores.append((linea, f"código repetido en el lote (líneas {', '.join(map(str, lineas))})"))
                normalizadas.pop(linea, None)

    # 2) aplicar fila a fila
    for linea, fila in filas:
        if linea not in normalizadas:
            continue
        canon = normalizadas[linea]
        error = _aplicar(db, edificio, canon, fila, rep, linea)
        if error:
            rep.errores.append((linea, error))

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return rep


def _aplicar(db: Session, ed: Edificio, canon: str, fila: dict, rep: ReporteStickers, linea: int) -> str | None:
    """Valida la fila completa y sólo entonces escribe: una fila nunca queda a medias."""
    unidad = db.scalar(select(Unidad).where(Unidad.edificio_id == ed.id, Unidad.numero == fila["depto"]))
    if unidad is None:
        return f"departamento '{fila['depto']}' no existe en el edificio"
    residente = None
    if fila.get("rut_residente"):
        if not validacion.rut_valido(fila["rut_residente"]):
            return f"RUT de residente inválido '{fila['rut_residente']}'"
        rut = validacion.rut_normalizar(fila["rut_residente"])
        residente = next((r for r in db.scalars(select(Residente).where(Residente.edificio_id == ed.id))
                          if validacion.rut_normalizar(r.rut) == rut), None)
        if residente is None or residente.unidad_id != unidad.id:
            return "el residente no existe o no pertenece a ese departamento"

    existente = db.scalar(select(Tag).where(Tag.uid == canon))
    if existente is not None and (existente.unidad_id != unidad.id or existente.edificio_id != ed.id):
        return "el sticker ya está registrado en otro departamento o edificio"

    pat = access.normalizar_patente(fila.get("patente", "")) if fila.get("patente") else ""
    veh = None
    if pat:
        error, veh = _validar_patente(db, ed, unidad, pat, existente)
        if error:
            return error

    # --- todo validado: escribir ---
    cambio = False
    if existente is None:
        try:
            tag = access.asignar_tag(db, ed, unidad.id, canon, TipoTag.vehicular,
                                     residente.id if residente else None,
                                     formato="wiegand" if canon.startswith("W") else "epc")
        except access.AccesoError as e:  # p. ej. el departamento ya tiene el máximo de stickers
            return str(e)
        rep.creados += 1
        cambio = True
    else:
        tag = existente
        if residente is not None and tag.residente_id != residente.id:
            tag.residente_id = residente.id
            cambio = True
    if pat:
        if veh is None:
            access.registrar_vehiculo(db, ed, unidad.id, pat, "", tag.id)
            rep.vinculados_patente += 1
            cambio = True
        elif veh.tag_id != tag.id:
            veh.tag_id = tag.id
            rep.vinculados_patente += 1
            cambio = True
    if existente is not None and not cambio:
        rep.sin_cambios += 1
    return None


def _validar_patente(db: Session, ed: Edificio, unidad: Unidad, pat: str, tag: Tag | None) -> tuple[str | None, Vehiculo | None]:
    if not 5 <= len(pat) <= 7:
        return "patente inválida", None
    veh = db.scalar(select(Vehiculo).where(Vehiculo.edificio_id == ed.id, Vehiculo.patente == pat))
    if veh is not None:
        if veh.unidad_id != unidad.id:
            return "la patente pertenece a otro departamento", None
        if veh.tag_id is not None and (tag is None or veh.tag_id != tag.id):
            return "la patente ya tiene otro sticker asociado", None
        return None, veh
    limite = min(unidad.estacionamientos, ed.max_estac_por_unidad)
    usados = db.scalar(select(func.count(Vehiculo.id)).where(Vehiculo.unidad_id == unidad.id,
                                                             Vehiculo.activo.is_(True)))
    if usados >= limite:
        return f"el departamento ya tiene {usados} vehículo(s) (máx. {limite})", None
    return None, None
