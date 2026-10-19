"""Stickers UHF: estado y fechas de tags; modo de acceso y tiempos por edificio; correlación de lecturas.

Revision ID: 0002_stickers
Revises: f1af332eaa4c
Create Date: 2026-10-19

Migración de datos: tags con activo=false pasan a estado 'bloqueado'; el resto queda 'activo'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_stickers"
down_revision: Union[str, None] = "f1af332eaa4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("tags") as b:
        b.add_column(sa.Column("estado", sa.String(12), nullable=False, server_default="activo"))
        b.add_column(sa.Column("formato", sa.String(12), nullable=False, server_default="epc"))
        b.add_column(sa.Column("fecha_alta", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("ultima_lectura", sa.DateTime(), nullable=True))
    op.execute("UPDATE tags SET estado = 'bloqueado' WHERE activo = 0 OR activo = false")
    op.execute("UPDATE tags SET fecha_alta = CURRENT_TIMESTAMP WHERE fecha_alta IS NULL")
    with op.batch_alter_table("tags") as b:
        b.alter_column("fecha_alta", nullable=False)
        b.drop_column("activo")

    with op.batch_alter_table("edificios") as b:
        b.add_column(sa.Column("modo_acceso", sa.String(30), nullable=False, server_default="sticker_o_patente"))
        b.add_column(sa.Column("ventana_coincidencia_s", sa.Integer(), nullable=False, server_default="10"))
        b.add_column(sa.Column("antirrebote_s", sa.Integer(), nullable=False, server_default="3"))
        b.add_column(sa.Column("anti_passback", sa.Boolean(), nullable=False, server_default=sa.false()))
        b.add_column(sa.Column("umbral_confianza_patente", sa.Float(), nullable=False, server_default="0.85"))

    with op.batch_alter_table("vehiculos") as b:
        b.add_column(sa.Column("adentro", sa.Boolean(), nullable=False, server_default=sa.false()))

    with op.batch_alter_table("accesos_log") as b:
        b.add_column(sa.Column("fuente", sa.String(12), nullable=False, server_default=""))
        b.alter_column("motivo", type_=sa.String(160), existing_type=sa.String(120))

    op.create_table(
        "lecturas_pendientes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(40), nullable=False),
        sa.Column("punto", sa.String(40), nullable=False),
        sa.Column("fuente", sa.String(12), nullable=False),
        sa.Column("valor", sa.String(80), nullable=False),
        sa.Column("vehiculo_id", sa.Integer(), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["vehiculo_id"], ["vehiculos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_lecturas_pendientes_edificio_id", "lecturas_pendientes", ["edificio_id"])


def downgrade() -> None:
    op.drop_index("ix_lecturas_pendientes_edificio_id", table_name="lecturas_pendientes")
    op.drop_table("lecturas_pendientes")
    with op.batch_alter_table("accesos_log") as b:
        b.alter_column("motivo", type_=sa.String(120), existing_type=sa.String(160))
        b.drop_column("fuente")
    with op.batch_alter_table("vehiculos") as b:
        b.drop_column("adentro")
    with op.batch_alter_table("edificios") as b:
        for c in ("umbral_confianza_patente", "anti_passback", "antirrebote_s", "ventana_coincidencia_s", "modo_acceso"):
            b.drop_column(c)
    with op.batch_alter_table("tags") as b:
        b.add_column(sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("UPDATE tags SET activo = CASE WHEN estado = 'activo' THEN 1 ELSE 0 END")
    with op.batch_alter_table("tags") as b:
        b.drop_column("ultima_lectura")
        b.drop_column("fecha_alta")
        b.drop_column("formato")
        b.drop_column("estado")
