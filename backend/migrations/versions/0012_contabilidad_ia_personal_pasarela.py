"""contabilidad pasarelas personal compromisos y registros

Revision ID: 0012_contabilidad_ia
Revises: 0011_comercial
Create Date: 2026-11-16 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_contabilidad_ia"
down_revision: Union[str, None] = "0011_comercial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "movimientos_contables",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("cuenta_debe", sa.String(length=60), nullable=False),
        sa.Column("cuenta_haber", sa.String(length=60), nullable=False),
        sa.Column("concepto", sa.String(length=200), nullable=False),
        sa.Column("monto", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("proveedor_id", sa.Integer(), nullable=True),
        sa.Column("documento_id", sa.Integer(), nullable=True),
        sa.Column("unidad_id", sa.Integer(), nullable=True),
        sa.Column("pago_id", sa.Integer(), nullable=True),
        sa.Column("creado_por", sa.Integer(), nullable=True),
        sa.Column("aprobado_por", sa.Integer(), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["aprobado_por"], ["residentes.id"]),
        sa.ForeignKeyConstraint(["creado_por"], ["residentes.id"]),
        sa.ForeignKeyConstraint(["documento_id"], ["documentos.id"]),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["pago_id"], ["pagos.id"]),
        sa.ForeignKeyConstraint(["proveedor_id"], ["proveedores.id"]),
        sa.ForeignKeyConstraint(["unidad_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("movimientos_contables", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_movimientos_contables_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_movimientos_contables_fecha"), ["fecha"], unique=False)
        batch_op.create_index(batch_op.f("ix_movimientos_contables_periodo"), ["periodo"], unique=False)
        batch_op.create_index(batch_op.f("ix_movimientos_contables_tipo"), ["tipo"], unique=False)

    op.create_table(
        "presupuestos_rubro",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("periodo", sa.String(length=7), nullable=False),
        sa.Column("categoria", sa.String(length=40), nullable=False),
        sa.Column("monto_presupuestado", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("notas", sa.String(length=300), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edificio_id", "periodo", "categoria"),
    )
    with op.batch_alter_table("presupuestos_rubro", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_presupuestos_rubro_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_presupuestos_rubro_periodo"), ["periodo"], unique=False)

    op.create_table(
        "convenios_pago",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("unidad_id", sa.Integer(), nullable=False),
        sa.Column("monto_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("pie_inicial", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("cuotas", sa.Integer(), nullable=False),
        sa.Column("cuotas_pagadas", sa.Integer(), nullable=False),
        sa.Column("tasa_interes_pct", sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column("primer_vencimiento", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("observaciones", sa.String(length=400), nullable=False),
        sa.Column("creado_por", sa.Integer(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["creado_por"], ["residentes.id"]),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["unidad_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("convenios_pago", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_convenios_pago_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_convenios_pago_unidad_id"), ["unidad_id"], unique=False)

    op.create_table(
        "transacciones_pasarela",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("unidad_id", sa.Integer(), nullable=False),
        sa.Column("residente_id", sa.Integer(), nullable=True),
        sa.Column("proveedor", sa.String(length=20), nullable=False),
        sa.Column("idempotencia", sa.String(length=64), nullable=False),
        sa.Column("orden_compra", sa.String(length=64), nullable=False),
        sa.Column("token_pasarela", sa.String(length=120), nullable=False),
        sa.Column("monto", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("moneda", sa.String(length=8), nullable=False),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("url_pago", sa.String(length=300), nullable=False),
        sa.Column("codigo_autorizacion", sa.String(length=40), nullable=False),
        sa.Column("pago_id", sa.Integer(), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.Column("confirmado_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["pago_id"], ["pagos.id"]),
        sa.ForeignKeyConstraint(["residente_id"], ["residentes.id"]),
        sa.ForeignKeyConstraint(["unidad_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edificio_id", "idempotencia"),
    )
    with op.batch_alter_table("transacciones_pasarela", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_transacciones_pasarela_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_transacciones_pasarela_orden_compra"), ["orden_compra"], unique=True)
        batch_op.create_index(batch_op.f("ix_transacciones_pasarela_token_pasarela"), ["token_pasarela"], unique=True)
        batch_op.create_index(batch_op.f("ix_transacciones_pasarela_unidad_id"), ["unidad_id"], unique=False)

    op.create_table(
        "trabajadores_edificio",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("rut", sa.String(length=15), nullable=False),
        sa.Column("cargo", sa.String(length=60), nullable=False),
        sa.Column("turno", sa.String(length=80), nullable=False),
        sa.Column("telefono", sa.String(length=20), nullable=False),
        sa.Column("email", sa.String(length=160), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("edificio_id", "rut"),
    )
    with op.batch_alter_table("trabajadores_edificio", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_trabajadores_edificio_edificio_id"), ["edificio_id"], unique=False)

    op.create_table(
        "asistencia_personal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("trabajador_id", sa.Integer(), nullable=False),
        sa.Column("fecha", sa.Date(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("entrada", sa.String(length=10), nullable=False),
        sa.Column("salida", sa.String(length=10), nullable=False),
        sa.Column("observacion", sa.String(length=300), nullable=False),
        sa.Column("registrado_por", sa.Integer(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["registrado_por"], ["residentes.id"]),
        sa.ForeignKeyConstraint(["trabajador_id"], ["trabajadores_edificio.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("asistencia_personal", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_asistencia_personal_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_asistencia_personal_fecha"), ["fecha"], unique=False)
        batch_op.create_index(batch_op.f("ix_asistencia_personal_trabajador_id"), ["trabajador_id"], unique=False)

    op.create_table(
        "compromisos_asamblea",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("asamblea_id", sa.Integer(), nullable=True),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("responsable_id", sa.Integer(), nullable=True),
        sa.Column("vencimiento", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("notas", sa.String(length=500), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["asamblea_id"], ["asambleas.id"]),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["responsable_id"], ["residentes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("compromisos_asamblea", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_compromisos_asamblea_asamblea_id"), ["asamblea_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_compromisos_asamblea_edificio_id"), ["edificio_id"], unique=False)

    op.create_table(
        "registros_comunidad",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("unidad_id", sa.Integer(), nullable=True),
        sa.Column("categoria", sa.String(length=30), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("rut", sa.String(length=15), nullable=False),
        sa.Column("contacto", sa.String(length=160), nullable=False),
        sa.Column("detalle", sa.String(length=500), nullable=False),
        sa.Column("desde", sa.Date(), nullable=True),
        sa.Column("hasta", sa.Date(), nullable=True),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["unidad_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("registros_comunidad", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_registros_comunidad_categoria"), ["categoria"], unique=False)
        batch_op.create_index(batch_op.f("ix_registros_comunidad_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_registros_comunidad_unidad_id"), ["unidad_id"], unique=False)

    op.create_table(
        "tokens_recuperacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("residente_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("usado", sa.Boolean(), nullable=False),
        sa.Column("expira", sa.DateTime(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["residente_id"], ["residentes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("tokens_recuperacion", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_tokens_recuperacion_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tokens_recuperacion_residente_id"), ["residente_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_tokens_recuperacion_token_hash"), ["token_hash"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("tokens_recuperacion", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_tokens_recuperacion_token_hash"))
        batch_op.drop_index(batch_op.f("ix_tokens_recuperacion_residente_id"))
        batch_op.drop_index(batch_op.f("ix_tokens_recuperacion_edificio_id"))
    op.drop_table("tokens_recuperacion")

    with op.batch_alter_table("registros_comunidad", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_registros_comunidad_unidad_id"))
        batch_op.drop_index(batch_op.f("ix_registros_comunidad_edificio_id"))
        batch_op.drop_index(batch_op.f("ix_registros_comunidad_categoria"))
    op.drop_table("registros_comunidad")

    with op.batch_alter_table("compromisos_asamblea", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_compromisos_asamblea_edificio_id"))
        batch_op.drop_index(batch_op.f("ix_compromisos_asamblea_asamblea_id"))
    op.drop_table("compromisos_asamblea")

    with op.batch_alter_table("asistencia_personal", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_asistencia_personal_trabajador_id"))
        batch_op.drop_index(batch_op.f("ix_asistencia_personal_fecha"))
        batch_op.drop_index(batch_op.f("ix_asistencia_personal_edificio_id"))
    op.drop_table("asistencia_personal")

    with op.batch_alter_table("trabajadores_edificio", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_trabajadores_edificio_edificio_id"))
    op.drop_table("trabajadores_edificio")

    with op.batch_alter_table("transacciones_pasarela", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_transacciones_pasarela_unidad_id"))
        batch_op.drop_index(batch_op.f("ix_transacciones_pasarela_token_pasarela"))
        batch_op.drop_index(batch_op.f("ix_transacciones_pasarela_orden_compra"))
        batch_op.drop_index(batch_op.f("ix_transacciones_pasarela_edificio_id"))
    op.drop_table("transacciones_pasarela")

    with op.batch_alter_table("convenios_pago", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_convenios_pago_unidad_id"))
        batch_op.drop_index(batch_op.f("ix_convenios_pago_edificio_id"))
    op.drop_table("convenios_pago")

    with op.batch_alter_table("presupuestos_rubro", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_presupuestos_rubro_periodo"))
        batch_op.drop_index(batch_op.f("ix_presupuestos_rubro_edificio_id"))
    op.drop_table("presupuestos_rubro")

    with op.batch_alter_table("movimientos_contables", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_movimientos_contables_tipo"))
        batch_op.drop_index(batch_op.f("ix_movimientos_contables_periodo"))
        batch_op.drop_index(batch_op.f("ix_movimientos_contables_fecha"))
        batch_op.drop_index(batch_op.f("ix_movimientos_contables_edificio_id"))
    op.drop_table("movimientos_contables")
