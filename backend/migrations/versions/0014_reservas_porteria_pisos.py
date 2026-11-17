"""Agrega piso en unidades, bloqueos de espacios comunes por mantenimiento y registros de porteria.

Revision ID: 0014_reservas_porteria_pisos
Revises: 0013_completar_18
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0014_reservas_porteria_pisos"
down_revision = "0013_completar_18"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unidades", sa.Column("piso", sa.Integer(), nullable=True))

    op.create_table(
        "bloqueos_espacio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("espacio_id", sa.Integer(), sa.ForeignKey("espacios_comunes.id"), nullable=False),
        sa.Column("desde", sa.DateTime(), nullable=False),
        sa.Column("hasta", sa.DateTime(), nullable=False),
        sa.Column("motivo", sa.String(200), nullable=False),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("residentes.id"), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_bloqueos_espacio_edificio_id", "bloqueos_espacio", ["edificio_id"])
    op.create_index("ix_bloqueos_espacio_espacio_id", "bloqueos_espacio", ["espacio_id"])

    op.create_table(
        "registros_porteria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("nombre", sa.String(120), nullable=False),
        sa.Column("empresa", sa.String(120), nullable=False, server_default=""),
        sa.Column("rut", sa.String(20), nullable=False, server_default=""),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=True),
        sa.Column("motivo", sa.String(200), nullable=False, server_default=""),
        sa.Column("entrada", sa.DateTime(), nullable=False),
        sa.Column("salida", sa.DateTime(), nullable=True),
        sa.Column("registrado_por", sa.Integer(), sa.ForeignKey("residentes.id"), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_registros_porteria_edificio_id", "registros_porteria", ["edificio_id"])
    op.create_index("ix_registros_porteria_tipo", "registros_porteria", ["tipo"])


def downgrade() -> None:
    op.drop_index("ix_registros_porteria_tipo", table_name="registros_porteria")
    op.drop_index("ix_registros_porteria_edificio_id", table_name="registros_porteria")
    op.drop_table("registros_porteria")
    op.drop_index("ix_bloqueos_espacio_espacio_id", table_name="bloqueos_espacio")
    op.drop_index("ix_bloqueos_espacio_edificio_id", table_name="bloqueos_espacio")
    op.drop_table("bloqueos_espacio")
    op.drop_column("unidades", "piso")
