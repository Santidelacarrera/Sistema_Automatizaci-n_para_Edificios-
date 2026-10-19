"""Alta y edición de residentes, tags y reglas desde el panel de administración.

Todas las funciones devuelven o lanzan ``AdminError`` con un mensaje listo para mostrar al usuario.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import rules, validacion
from ..models import Edificio, EstadoTag, Evento, Regla, Residente, Rol, Tag, TipoTag, Unidad, Vehiculo
from ..security import hash_password
from . import access


class AdminError(Exception):
    """Error de validación (422) o de duplicado/conflicto (409). ``str(e)`` es el mensaje para el panel."""

    def __init__(self, msg: str, status: int = 422):
        super().__init__(msg)
        self.status = status


def _errores(errs: list[str]) -> None:
    if errs:
        raise AdminError("; ".join(errs))


def _unidad_del_edificio(db: Session, edificio_id: str, unidad_id: int) -> Unidad:
    u = db.get(Unidad, unidad_id)
    if not u or u.edificio_id != edificio_id:
        raise AdminError("El departamento no existe en este edificio")
    return u


def _rut_ocupado(db: Session, edificio_id: str, rut: str, excluir_id: int | None) -> bool:
    for r in db.scalars(select(Residente).where(Residente.edificio_id == edificio_id)):
        if r.id != excluir_id and validacion.rut_normalizar(r.rut) == rut:
            return True
    return False


def validar_residente(db: Session, ed: Edificio, datos: dict, actual: Residente | None = None,
                      campos: set[str] | None = None) -> dict:
    """Valida y normaliza un residente. ``datos`` trae todos los campos ya combinados.

    En edición, ``campos`` indica qué cambió: sólo esos se validan, así un dato antiguo imperfecto
    (p. ej. un RUT mal digitado hace años) no impide corregir otro campo. Devuelve el dict listo para guardar.
    """
    def cambia(campo: str) -> bool:
        return campos is None or campo in campos

    errs = []
    nombre = (datos.get("nombre") or "").strip()
    if cambia("nombre"):
        if not nombre:
            errs.append("El nombre es obligatorio")
        if len(nombre) > 120:
            errs.append("El nombre no puede tener más de 120 caracteres")
    rut_crudo = datos.get("rut") or ""
    if cambia("rut") and not validacion.rut_valido(rut_crudo):
        errs.append("RUT inválido: revisa el dígito verificador")
    email = (datos.get("email") or "").strip()
    if cambia("email") and email and not validacion.email_valido(email):
        errs.append("Correo inválido")
    telefono = datos.get("telefono") or ""
    if cambia("telefono") and telefono and not validacion.telefono_valido(telefono):
        errs.append("Teléfono inválido: entre 8 y 15 dígitos (el celular se completa con +56)")
    rol = datos.get("rol", Rol.residente)
    if cambia("rol") and rol == Rol.superadmin:
        errs.append("El rol superadmin no se asigna desde el edificio")
    _errores(errs)

    rut = validacion.rut_normalizar(rut_crudo) if cambia("rut") else datos["rut"]
    if cambia("rut") and _rut_ocupado(db, ed.id, rut, actual.id if actual else None):
        raise AdminError(f"El RUT {validacion.rut_formato(rut)} ya está registrado en este edificio", 409)
    if cambia("unidad_id"):
        _unidad_del_edificio(db, ed.id, datos["unidad_id"])
    if actual and actual.rol == Rol.admin and actual.activo and (rol != Rol.admin or not datos.get("activo", True)):
        otros = db.scalar(select(func.count(Residente.id)).where(
            Residente.edificio_id == ed.id, Residente.rol == Rol.admin, Residente.activo.is_(True),
            Residente.id != actual.id))
        if not otros:
            raise AdminError("Debe quedar al menos un administrador activo en el edificio", 409)
    return {"nombre": nombre, "rut": rut, "email": email, "telefono": validacion.telefono_normalizar(telefono),
            "unidad_id": datos["unidad_id"], "rol": rol, "activo": bool(datos.get("activo", True))}


def crear_residente(db: Session, ed: Edificio, datos: dict, password: str | None) -> Residente:
    limpio = validar_residente(db, ed, datos)
    r = Residente(edificio_id=ed.id, password_hash=hash_password(password) if password else "", **limpio)
    db.add(r)
    db.flush()
    return r


def editar_residente(db: Session, ed: Edificio, r: Residente, cambios: dict, password: str | None) -> Residente:
    actual = {"nombre": r.nombre, "rut": r.rut, "email": r.email, "telefono": r.telefono,
              "unidad_id": r.unidad_id, "rol": r.rol, "activo": r.activo}
    limpio = validar_residente(db, ed, actual | cambios, actual=r, campos=set(cambios))
    for campo, valor in limpio.items():
        setattr(r, campo, valor)
    if password:
        r.password_hash = hash_password(password)
    db.flush()
    return r


def editar_tag(db: Session, ed: Edificio, tag: Tag, cambios: dict) -> Tag:
    if "residente_id" in cambios and cambios["residente_id"] is not None:
        r = db.get(Residente, cambios["residente_id"])
        if not r or r.edificio_id != ed.id or r.unidad_id != tag.unidad_id:
            raise AdminError("El residente debe pertenecer al mismo departamento del tag")
    if "residente_id" in cambios:
        tag.residente_id = cambios["residente_id"]
    if "activo" in cambios:
        tag.activo = bool(cambios["activo"])
    db.flush()
    return tag


def alta_tag(db: Session, ed: Edificio, datos: dict) -> Tag:
    try:
        return access.asignar_tag(db, ed, datos["unidad_id"], datos["uid"], TipoTag(datos["tipo"]),
                                  datos.get("residente_id"))
    except access.AccesoError as e:
        raise AdminError(str(e), e.status)


def validar_y_guardar_regla(db: Session, ed: Edificio, regla, cambios: dict):
    """Crea (``regla`` None) o edita una regla. ``cambios`` sólo trae los campos que llegaron."""
    if regla is None:
        datos = {"accion": cambios["accion"], "tipo": cambios["tipo"], "params": cambios.get("params") or {},
                 "activa": True}
        excluir = None
    else:
        datos = {"accion": regla.accion, "tipo": regla.tipo, "params": regla.params, "activa": regla.activa} | cambios
        excluir = regla.id
    _errores(rules.validar_regla(db, ed.id, datos["accion"], datos["tipo"], datos["params"], excluir))
    if regla is None:
        regla = Regla(edificio_id=ed.id, **datos)
        db.add(regla)
    else:
        regla.tipo, regla.params, regla.activa = datos["tipo"], datos["params"], bool(datos["activa"])
    db.flush()
    return regla


def vincular_sticker(db: Session, ed: Edificio, tag: Tag, vehiculo_id: int) -> Tag:
    """Asocia el sticker a una patente del mismo departamento. Un sticker sirve para un solo vehículo."""
    v = db.get(Vehiculo, vehiculo_id)
    if not v or v.edificio_id != ed.id:
        raise AdminError("Vehículo no existe en este edificio", 404)
    if v.unidad_id != tag.unidad_id:
        raise AdminError("El vehículo es de otro departamento que el sticker", 422)
    if not v.activo:
        raise AdminError("El vehículo está dado de baja", 422)
    if v.tag_id is not None and v.tag_id != tag.id:
        raise AdminError("Ese vehículo ya tiene otro sticker: desvincúlalo primero", 409)
    otro = db.scalar(select(Vehiculo).where(Vehiculo.tag_id == tag.id, Vehiculo.id != v.id))
    if otro is not None:
        raise AdminError(f"El sticker ya está asociado a la patente {otro.patente}: desvincúlalo primero", 409)
    v.tag_id = tag.id
    db.add(Evento(edificio_id=ed.id, tipo="tag.vinculado", payload={"tag_id": tag.id, "vehiculo_id": v.id}))
    db.flush()
    return tag


def desvincular_sticker(db: Session, ed: Edificio, tag: Tag) -> Tag:
    for v in db.scalars(select(Vehiculo).where(Vehiculo.tag_id == tag.id)):
        v.tag_id = None
    db.add(Evento(edificio_id=ed.id, tipo="tag.desvinculado", payload={"tag_id": tag.id}))
    db.flush()
    return tag


def cambiar_estado_tag(db: Session, ed: Edificio, tag: Tag, estado: str, motivo: str = "") -> Tag:
    """Activa, marca perdido o bloquea un sticker. Queda en la bitácora; surte efecto en la siguiente lectura."""
    anterior = tag.estado
    tag.estado = estado
    db.add(Evento(edificio_id=ed.id, tipo="tag.estado",
                  payload={"tag_id": tag.id, "de": anterior, "a": estado, "motivo": motivo[:200]}))
    db.flush()
    return tag


def reasignar_tag(db: Session, ed: Edificio, tag: Tag, unidad_id: int, residente_id: int | None,
                  vehiculo_id: int | None) -> Tag:
    """Pasa el sticker a otro departamento. El vehículo que lo tenía queda sin sticker."""
    _unidad_del_edificio(db, ed.id, unidad_id)
    if residente_id is not None:
        r = db.get(Residente, residente_id)
        if not r or r.edificio_id != ed.id or r.unidad_id != unidad_id:
            raise AdminError("El residente debe pertenecer al departamento de destino", 422)
    for v in db.scalars(select(Vehiculo).where(Vehiculo.tag_id == tag.id)):
        v.tag_id = None
    if vehiculo_id is not None:
        v = db.get(Vehiculo, vehiculo_id)
        if not v or v.edificio_id != ed.id or v.unidad_id != unidad_id or not v.activo:
            raise AdminError("El vehículo debe ser activo y del departamento de destino", 422)
        v.tag_id = tag.id
    anterior = tag.unidad_id
    tag.unidad_id, tag.residente_id = unidad_id, residente_id
    db.add(Evento(edificio_id=ed.id, tipo="tag.reasignado",
                  payload={"tag_id": tag.id, "de_unidad": anterior, "a_unidad": unidad_id}))
    db.flush()
    return tag
