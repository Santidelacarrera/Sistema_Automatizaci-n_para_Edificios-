"""Derechos de los titulares (acceso y supresión) sobre los datos de un residente.

Esto implementa la mecánica; los plazos y excepciones legales (p. ej. conservar registros
contables) los define la administración con su abogado. Ver docs/PRIVACIDAD.md.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Cargo, Residente, Tag, Vehiculo
from ..validacion import rut_formato


def exportar(db: Session, r: Residente) -> dict:
    """Copia legible de lo que el sistema guarda de la persona y de su departamento."""
    tags = db.scalars(select(Tag).where(Tag.residente_id == r.id)).all()
    vehiculos = db.scalars(select(Vehiculo).where(Vehiculo.unidad_id == r.unidad_id, Vehiculo.activo.is_(True))).all()
    cargos = db.scalars(select(Cargo).where(Cargo.unidad_id == r.unidad_id).order_by(Cargo.periodo)).all()
    return {
        "residente": {"nombre": r.nombre, "rut": rut_formato(r.rut), "email": r.email, "telefono": r.telefono,
                      "rol": r.rol.value, "activo": r.activo, "unidad": r.unidad.numero},
        "tags": [{"codigo": t.uid, "tipo": t.tipo.value, "estado": t.estado.value} for t in tags],
        "vehiculos_de_la_unidad": [{"patente": v.patente, "descripcion": v.descripcion} for v in vehiculos],
        "cargos_de_la_unidad": [{"periodo": c.periodo, "concepto": c.concepto, "monto": float(c.monto),
                                 "saldo": float(c.saldo)} for c in cargos],
    }


def anonimizar(db: Session, r: Residente) -> None:
    """Borra los datos que identifican a la persona y le quita el acceso.

    Se conservan los cargos y pagos del departamento (obligación contable) y los vehículos, que
    pertenecen a la unidad. Los tags de la persona quedan bloqueados.
    """
    from ..models import EstadoTag
    for t in db.scalars(select(Tag).where(Tag.residente_id == r.id)):
        t.estado = EstadoTag.bloqueado
    r.nombre, r.rut, r.email, r.telefono = "[eliminado]", "", "", ""
    r.password_hash, r.activo = "", False
