"""Carga inicial de un edificio: edificio, departamentos y administrador.

Requiere la base ya migrada (``alembic upgrade head``). Ejemplos:

    python scripts/seed.py --archivo edificio.yaml
    python scripts/seed.py --id edificio_a --nombre "Edificio A" --departamentos 101,102,103 \\
        --admin-nombre "Ana Pérez" --admin-rut 12345678-5 --admin-email ana@x.cl --admin-unidad 101

Los flags sobrescriben lo que venga del YAML. La contraseña del administrador sale de
``--admin-password`` o de la variable ``SEED_ADMIN_PASSWORD``; si no se entrega ninguna, se genera
y se imprime una sola vez. La clave de dispositivo (X-Device-Key) siempre es aleatoria.
Nunca se escriben secretos en el repositorio: el YAML no admite contraseñas.
"""
import argparse
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from app import validacion  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Edificio, Residente, Rol, Unidad  # noqa: E402
from app.security import hash_password  # noqa: E402

RE_ID = re.compile(r"^[a-z0-9_]{3,40}$")
RE_CODIGO = re.compile(r"^CC-[A-Z0-9]+-[A-Z0-9]+$")  # el conciliador (services/reconciliation.py) lo reconoce


def _slug(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


def construir_config(args: argparse.Namespace) -> dict:
    """Combina YAML y flags en una sola configuración. Los flags ganan."""
    cfg = {}
    if args.archivo:
        with open(args.archivo, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    ed = dict(cfg.get("edificio") or {})
    ad = dict(cfg.get("administrador") or {})
    deptos = [dict(d) for d in (cfg.get("departamentos") or [])]
    for clave, valor in (("id", args.id), ("nombre", args.nombre), ("cupos_visitas", args.cupos_visitas),
                         ("max_estac_por_unidad", args.max_estac), ("tolerancia_visita_min", args.tolerancia)):
        if valor is not None:
            ed[clave] = valor
    for clave, valor in (("nombre", args.admin_nombre), ("rut", args.admin_rut),
                         ("email", args.admin_email), ("telefono", args.admin_telefono),
                         ("unidad", args.admin_unidad)):
        if valor is not None:
            ad[clave] = valor
    if args.departamentos:
        numeros = [n.strip() for n in args.departamentos.split(",") if n.strip()]
        coef = round(1 / len(numeros), 6) if numeros else 0
        deptos = [{"numero": n, "coeficiente": coef, "estacionamientos": 0} for n in numeros]
    return {"edificio": ed, "administrador": ad, "departamentos": deptos}


def validar_config(cfg: dict) -> tuple[list[str], list[str]]:
    """Devuelve (errores, advertencias). Con errores no se crea nada."""
    errores, avisos = [], []
    ed, ad, deptos = cfg["edificio"], cfg["administrador"], cfg["departamentos"]
    eid = str(ed.get("id", ""))
    if not RE_ID.match(eid):
        errores.append("edificio.id: usar minúsculas, números o guion bajo (3 a 40 caracteres)")
    if not str(ed.get("nombre", "")).strip():
        errores.append("edificio.nombre es obligatorio")
    if not deptos:
        errores.append("Se requiere al menos un departamento")
    numeros, suma = set(), 0.0
    for i, d in enumerate(deptos, 1):
        numero = str(d.get("numero", "")).strip()
        if not numero:
            errores.append(f"departamento {i}: falta numero")
            continue
        if numero in numeros:
            errores.append(f"departamento {numero}: repetido")
        numeros.add(numero)
        try:
            coef = float(d.get("coeficiente", 0))
        except (TypeError, ValueError):
            coef = 0.0
        if not 0 < coef <= 1:
            errores.append(f"departamento {numero}: coeficiente debe estar entre 0 y 1")
        suma += max(coef, 0)
        est = d.get("estacionamientos", 0)
        if not isinstance(est, int) or est < 0:
            errores.append(f"departamento {numero}: estacionamientos debe ser un entero >= 0")
        codigo = str(d.get("codigo_cobro") or f"CC-{_slug(eid)}-{_slug(numero)}").upper()
        if not RE_CODIGO.match(codigo):
            errores.append(f"departamento {numero}: codigo_cobro '{codigo}' debe tener la forma CC-XXXX-NNN")
    if deptos and abs(suma - 1) > 0.001:
        avisos.append(f"Los coeficientes suman {suma:.6f}, no 1: revisar la copropiedad")
    if not str(ad.get("nombre", "")).strip():
        errores.append("administrador.nombre es obligatorio")
    if not validacion.rut_valido(str(ad.get("rut", ""))):
        errores.append("administrador.rut inválido (dígito verificador)")
    if ad.get("email") and not validacion.email_valido(str(ad["email"])):
        errores.append("administrador.email inválido")
    if ad.get("telefono") and not validacion.telefono_valido(str(ad["telefono"])):
        errores.append("administrador.telefono inválido (8 a 15 dígitos)")
    if str(ad.get("unidad", "")) not in numeros:
        errores.append("administrador.unidad debe ser un departamento de la lista")
    return errores, avisos


def crear(db, cfg: dict, password: str) -> dict:
    """Crea el edificio, sus unidades y el administrador en una sola transacción."""
    ed_cfg, ad_cfg = cfg["edificio"], cfg["administrador"]
    eid = str(ed_cfg["id"])
    clave_dispositivo = secrets.token_urlsafe(32)
    edificio = Edificio(id=eid, nombre=str(ed_cfg["nombre"]).strip(),
                        cupos_visitas=int(ed_cfg.get("cupos_visitas", 6)),
                        max_estac_por_unidad=int(ed_cfg.get("max_estac_por_unidad", 2)),
                        tolerancia_visita_min=int(ed_cfg.get("tolerancia_visita_min", 20)),
                        device_api_key=clave_dispositivo)
    db.add(edificio)
    db.flush()
    unidades = {}
    for d in cfg["departamentos"]:
        numero = str(d["numero"]).strip()
        u = Unidad(edificio_id=eid, numero=numero, coeficiente=float(d["coeficiente"]),
                   estacionamientos=int(d.get("estacionamientos", 0)),
                   codigo_cobro=str(d.get("codigo_cobro") or f"CC-{_slug(eid)}-{_slug(numero)}").upper())
        db.add(u)
        unidades[numero] = u
    db.flush()
    admin = Residente(edificio_id=eid, unidad_id=unidades[str(ad_cfg["unidad"])].id,
                      nombre=str(ad_cfg["nombre"]).strip(), rut=validacion.rut_normalizar(str(ad_cfg["rut"])),
                      email=str(ad_cfg.get("email") or ""),
                      telefono=validacion.telefono_normalizar(str(ad_cfg.get("telefono") or "")),
                      password_hash=hash_password(password), rol=Rol.admin)
    db.add(admin)
    db.commit()
    return {"edificio": eid, "unidades": len(unidades), "device_api_key": clave_dispositivo}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Carga inicial de un edificio (edificio, departamentos y administrador).")
    p.add_argument("--archivo", help="YAML con edificio, administrador y departamentos")
    p.add_argument("--id", help="id del edificio, p.ej. edificio_a")
    p.add_argument("--nombre")
    p.add_argument("--cupos-visitas", type=int, dest="cupos_visitas")
    p.add_argument("--max-estac", type=int, dest="max_estac")
    p.add_argument("--tolerancia", type=int, help="minutos de tolerancia para visitas (no-show)")
    p.add_argument("--departamentos", help="lista separada por comas, p.ej. 101,102,103 (coeficiente igual)")
    p.add_argument("--admin-nombre", dest="admin_nombre")
    p.add_argument("--admin-rut", dest="admin_rut")
    p.add_argument("--admin-email", dest="admin_email")
    p.add_argument("--admin-telefono", dest="admin_telefono")
    p.add_argument("--admin-unidad", dest="admin_unidad", help="número del departamento del administrador")
    p.add_argument("--admin-password", dest="admin_password",
                   help="preferible usar SEED_ADMIN_PASSWORD para no dejarla en el historial de la shell")
    args = p.parse_args(argv)

    if not inspect(engine).has_table("edificios"):
        print("La base no tiene tablas. Ejecuta primero: alembic upgrade head", file=sys.stderr)
        return 1
    cfg = construir_config(args)
    errores, avisos = validar_config(cfg)
    for a in avisos:
        print(f"AVISO: {a}")
    if errores:
        for e in errores:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        if db.get(Edificio, str(cfg["edificio"]["id"])):
            print(f"ERROR: el edificio '{cfg['edificio']['id']}' ya existe; no se sobrescribe.", file=sys.stderr)
            return 1
        password = args.admin_password or os.getenv("SEED_ADMIN_PASSWORD") or ""
        generada = not password
        if generada:
            password = secrets.token_urlsafe(12)
        elif len(password) < 8:
            print("ERROR: la contraseña del administrador debe tener al menos 8 caracteres.", file=sys.stderr)
            return 1
        try:
            res = crear(db, cfg, password)
        except SQLAlchemyError as e:
            db.rollback()
            print(f"ERROR de base de datos (se revirtió todo): {e.__class__.__name__}: {e.orig}", file=sys.stderr)
            return 1

    print(f"Edificio '{res['edificio']}' creado con {res['unidades']} departamento(s).")
    print(f"X-Device-Key (lectores): {res['device_api_key']}")
    if generada:
        print(f"Contraseña generada del administrador: {password}")
    print("Guarda estos valores ahora: no volverán a mostrarse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
