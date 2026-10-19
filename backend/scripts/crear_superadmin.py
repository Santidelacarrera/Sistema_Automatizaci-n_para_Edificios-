"""Crea un superadmin (ve y administra todos los edificios). Requiere el edificio base ya cargado.

    python scripts/crear_superadmin.py --edificio edificio_a --nombre "Soporte" --rut 12345678-5 \
        --email soporte@empresa.cl            (contraseña por SUPERADMIN_PASSWORD o pedida al generar)
"""
import argparse
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import validacion  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import Edificio, Residente, Rol, Unidad  # noqa: E402
from app.security import hash_password  # noqa: E402


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Crea un superadmin.")
    p.add_argument("--edificio", required=True, help="edificio donde inicia sesión (su base)")
    p.add_argument("--unidad", required=True, help="número de departamento de la base")
    p.add_argument("--nombre", required=True)
    p.add_argument("--rut", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", default=os.getenv("SUPERADMIN_PASSWORD", ""))
    a = p.parse_args(argv)
    errores = []
    if not validacion.rut_valido(a.rut):
        errores.append("RUT inválido")
    if not validacion.email_valido(a.email):
        errores.append("correo inválido")
    if a.password and len(a.password) < 12:
        errores.append("la contraseña del superadmin debe tener al menos 12 caracteres")
    if errores:
        print("ERROR: " + "; ".join(errores), file=sys.stderr)
        return 1
    generada = not a.password
    password = a.password or secrets.token_urlsafe(16)
    with SessionLocal() as db:
        ed = db.get(Edificio, a.edificio)
        u = db.query(Unidad).filter_by(edificio_id=a.edificio, numero=a.unidad).one_or_none() if ed else None
        if not ed or not u:
            print("ERROR: edificio o departamento inexistente", file=sys.stderr)
            return 1
        rut = validacion.rut_normalizar(a.rut)
        if any(validacion.rut_normalizar(r.rut) == rut for r in db.query(Residente).filter_by(edificio_id=a.edificio)):
            print("ERROR: ese RUT ya existe en el edificio", file=sys.stderr)
            return 1
        db.add(Residente(edificio_id=a.edificio, unidad_id=u.id, nombre=a.nombre.strip(), rut=rut,
                         email=a.email.strip(), password_hash=hash_password(password), rol=Rol.superadmin))
        db.commit()
    print(f"Superadmin creado: {a.email} (inicia sesión en el edificio {a.edificio}).")
    if generada:
        print(f"Contraseña generada (se muestra una sola vez): {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
