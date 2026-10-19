"""Importa departamentos y residentes desde CSV. Idempotente y con errores reportados por línea.

    python scripts/importar_csv.py --edificio edificio_a departamentos.csv [--dry-run]

Columnas (cabecera obligatoria, orden libre, separador ',' o ';' detectado, UTF-8 con o sin BOM):

  numero             Departamento que la fila define o referencia. Obligatoria.
  coeficiente        Decimal (acepta coma). Obligatoria al crear un departamento nuevo.
  estacionamientos   Entero >= 0. Opcional (0 por defecto).
  codigo_cobro       Forma CC-XXXX-NNN (la usa el conciliador). Obligatoria al crear un departamento.
  nombre             Nombre del residente.
  rut                RUT con dígito verificador. Obligatorio si la fila trae residente.
  email, telefono    Opcionales; se validan si vienen.
  depto              Departamento del residente. Si falta, se usa numero.

Una fila puede definir un departamento (coeficiente/codigo_cobro), un residente (nombre/rut) o ambos.
Primero se aplican los departamentos y luego los residentes, así un residente puede apuntar a un
departamento que aparece más abajo. Las filas inválidas se reportan y no detienen al resto.
Los residentes se identifican por RUT dentro del edificio: reimportar el mismo archivo no duplica nada.
Exit code: 0 sin errores, 1 si hubo filas rechazadas (las válidas igual se importan), 2 si no se pudo leer.
"""
import argparse
import csv
import io
import os
import re
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from app import validacion  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Edificio, Residente, Rol, Unidad  # noqa: E402

RE_CODIGO = re.compile(r"^CC-[A-Z0-9]+-[A-Z0-9]+$")
CAMPOS_UNIDAD = ("coeficiente", "estacionamientos", "codigo_cobro")


@dataclass
class Reporte:
    unidades_creadas: int = 0
    unidades_actualizadas: int = 0
    residentes_creados: int = 0
    residentes_actualizados: int = 0
    sin_cambios: int = 0
    errores: list[tuple[int, str]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)


def _normalizar_cabeceras(fila: dict) -> dict:
    return {(k or "").strip().lower(): (v or "").strip() for k, v in fila.items()}


def _detectar_separador(texto: str) -> str:
    primera = texto.splitlines()[0] if texto.strip() else ""
    return ";" if primera.count(";") > primera.count(",") else ","


def leer_filas(texto: str) -> tuple[list[tuple[int, dict]], list[tuple[int, str]]]:
    """Devuelve ([(linea, fila)], errores_de_cabecera). Sin cabecera 'numero' no hay nada que importar."""
    texto = texto.lstrip("﻿")
    lector = csv.DictReader(io.StringIO(texto), delimiter=_detectar_separador(texto))
    if not lector.fieldnames or "numero" not in [c.strip().lower() for c in lector.fieldnames]:
        return [], [(1, "La cabecera debe incluir la columna 'numero'")]
    return [(lector.line_num, _normalizar_cabeceras(f)) for f in lector if any(f.values())], []


def _unidad_fila(fila: dict, eid: str, linea: int, rep: Reporte) -> dict | None:
    """Valida los datos de departamento de una fila. None si la fila no define departamento o si tiene errores."""
    if not any(fila.get(c) for c in CAMPOS_UNIDAD):
        return None
    datos = {"numero": fila["numero"][:20]}
    try:
        coef = fila.get("coeficiente", "").replace(",", ".")
        datos["coeficiente"] = float(coef) if coef else None
        if datos["coeficiente"] is not None and not 0 < datos["coeficiente"] <= 1:
            raise ValueError
    except ValueError:
        rep.errores.append((linea, f"coeficiente inválido '{fila.get('coeficiente')}' (decimal entre 0 y 1)"))
        return None
    try:
        est = fila.get("estacionamientos", "")
        datos["estacionamientos"] = int(est) if est else None  # None = no tocar el valor existente
        if datos["estacionamientos"] is not None and datos["estacionamientos"] < 0:
            raise ValueError
    except ValueError:
        rep.errores.append((linea, f"estacionamientos inválido '{fila.get('estacionamientos')}' (entero >= 0)"))
        return None
    codigo = fila.get("codigo_cobro", "").upper()
    if codigo and not RE_CODIGO.match(codigo):
        rep.errores.append((linea, f"codigo_cobro '{codigo}' debe tener la forma CC-XXXX-NNN"))
        return None
    datos["codigo_cobro"] = codigo or None
    return datos


def _residente_fila(fila: dict, linea: int, rep: Reporte) -> dict | None:
    """Valida los datos de residente. None si la fila no trae residente o si tiene errores."""
    if not (fila.get("nombre") or fila.get("rut")):
        return None
    if not fila.get("nombre"):
        rep.errores.append((linea, "residente sin nombre"))
        return None
    if not validacion.rut_valido(fila.get("rut", "")):
        rep.errores.append((linea, f"RUT inválido '{fila.get('rut', '')}' (revisa el dígito verificador)"))
        return None
    if fila.get("email") and not validacion.email_valido(fila["email"]):
        rep.errores.append((linea, f"email inválido '{fila['email']}'"))
        return None
    if fila.get("telefono") and not validacion.telefono_valido(fila["telefono"]):
        rep.errores.append((linea, f"teléfono inválido '{fila['telefono']}' (8 a 15 dígitos)"))
        return None
    return {"nombre": fila["nombre"][:120], "rut": validacion.rut_normalizar(fila["rut"]),
            "email": fila.get("email", "")[:160], "telefono": validacion.telefono_normalizar(fila.get("telefono", "")),
            "depto": (fila.get("depto") or fila.get("numero", ""))[:20]}


def importar(db, edificio_id: str, texto: str, dry_run: bool = False) -> Reporte:
    rep = Reporte()
    filas, err_cab = leer_filas(texto)
    rep.errores.extend(err_cab)
    if err_cab:
        return rep

    # Pasada 1: departamentos.
    unidades_db = {u.numero: u for u in db.scalars(select(Unidad).where(Unidad.edificio_id == edificio_id))}
    codigos_archivo, definidos = {}, set()
    for linea, fila in filas:
        if not fila.get("numero"):
            if any(fila.get(c) for c in CAMPOS_UNIDAD):
                rep.errores.append((linea, "fila con datos de departamento pero sin 'numero'"))
            continue  # fila sólo de residente: se resuelve en la pasada 2 con 'depto'
        datos = _unidad_fila(fila, edificio_id, linea, rep)
        if datos is None:  # fila sin datos de departamento, o con errores ya reportados
            continue
        numero = datos["numero"]
        if numero in definidos:
            rep.errores.append((linea, f"departamento {numero} definido más de una vez en el archivo"))
            continue
        existente = unidades_db.get(numero)
        if existente is None and (datos["coeficiente"] is None or not datos["codigo_cobro"]):
            rep.errores.append((linea, f"departamento nuevo {numero}: requiere coeficiente y codigo_cobro"))
            continue
        codigo = datos["codigo_cobro"]
        if codigo:
            if codigos_archivo.get(codigo, numero) != numero:
                rep.errores.append((linea, f"codigo_cobro {codigo} repetido en el archivo"))
                continue
            dueno = db.scalar(select(Unidad).where(Unidad.codigo_cobro == codigo))  # es global en la base
            if dueno and not (dueno.edificio_id == edificio_id and dueno.numero == numero):
                rep.errores.append((linea, f"codigo_cobro {codigo} ya lo usa otro departamento"))
                continue
            codigos_archivo[codigo] = numero
        definidos.add(numero)
        if existente is None:
            u = Unidad(edificio_id=edificio_id, numero=numero, coeficiente=datos["coeficiente"],
                       estacionamientos=datos["estacionamientos"] or 0, codigo_cobro=codigo)
            db.add(u)
            db.flush()
            unidades_db[numero] = u
            rep.unidades_creadas += 1
            continue
        cambios = False
        if datos["coeficiente"] is not None and abs(float(existente.coeficiente) - datos["coeficiente"]) > 1e-9:
            existente.coeficiente, cambios = datos["coeficiente"], True
        if datos["estacionamientos"] is not None and existente.estacionamientos != datos["estacionamientos"]:
            existente.estacionamientos, cambios = datos["estacionamientos"], True
        if codigo and existente.codigo_cobro != codigo:
            existente.codigo_cobro, cambios = codigo, True
        if cambios:
            rep.unidades_actualizadas += 1
        else:
            rep.sin_cambios += 1

    # Pasada 2: residentes (identificados por RUT dentro del edificio).
    residentes_db = {validacion.rut_normalizar(r.rut): r for r in
                     db.scalars(select(Residente).where(Residente.edificio_id == edificio_id))}
    for linea, fila in filas:
        datos = _residente_fila(fila, linea, rep)
        if datos is None:
            continue
        if not datos["depto"]:
            rep.errores.append((linea, "residente sin departamento: usa las columnas 'depto' o 'numero'"))
            continue
        unidad = unidades_db.get(datos["depto"])
        if unidad is None:
            rep.errores.append((linea, f"departamento '{datos['depto']}' no existe en el edificio"))
            continue
        existente = residentes_db.get(datos["rut"])
        if existente is None:
            r = Residente(edificio_id=edificio_id, unidad_id=unidad.id, nombre=datos["nombre"], rut=datos["rut"],
                          email=datos["email"], telefono=datos["telefono"], rol=Rol.residente)
            db.add(r)
            db.flush()
            residentes_db[datos["rut"]] = r
            rep.residentes_creados += 1
            continue
        cambios = False
        for campo, valor in (("nombre", datos["nombre"]), ("email", datos["email"]),
                             ("telefono", datos["telefono"]), ("unidad_id", unidad.id)):
            if getattr(existente, campo) != valor:
                setattr(existente, campo, valor)
                cambios = True
        if cambios:
            rep.residentes_actualizados += 1
        else:
            rep.sin_cambios += 1

    coef_total = sum(float(u.coeficiente) for u in unidades_db.values())
    if unidades_db and abs(coef_total - 1) > 0.001:
        rep.avisos.append(f"Los coeficientes del edificio suman {coef_total:.6f}, no 1")
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return rep


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Importa departamentos y residentes desde CSV.")
    p.add_argument("archivo")
    p.add_argument("--edificio", required=True, help="id del edificio destino")
    p.add_argument("--dry-run", action="store_true", help="valida y reporta sin escribir")
    args = p.parse_args(argv)
    try:
        with open(args.archivo, encoding="utf-8-sig") as f:
            texto = f.read()
    except (OSError, UnicodeDecodeError) as e:
        print(f"No se pudo leer el archivo: {e}", file=sys.stderr)
        return 2
    with SessionLocal() as db:
        if not db.get(Edificio, args.edificio):
            print(f"El edificio '{args.edificio}' no existe.", file=sys.stderr)
            return 2
        rep = importar(db, args.edificio, texto, dry_run=args.dry_run)
    modo = " (simulación, nada se escribió)" if args.dry_run else ""
    print(f"Departamentos: {rep.unidades_creadas} creados, {rep.unidades_actualizadas} actualizados{modo}")
    print(f"Residentes: {rep.residentes_creados} creados, {rep.residentes_actualizados} actualizados{modo}")
    print(f"Sin cambios: {rep.sin_cambios}")
    for a in rep.avisos:
        print(f"AVISO: {a}")
    for linea, msg in sorted(rep.errores):
        print(f"Línea {linea}: {msg}", file=sys.stderr)
    if rep.errores:
        print(f"{len(rep.errores)} fila(s) rechazada(s).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
