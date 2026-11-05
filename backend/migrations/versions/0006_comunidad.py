"""Comunidad: comunicados, encomiendas, avisos de pago, aforo de espacios

Revision ID: 0006_comunidad
Revises: 0005_conversaciones_wa
Create Date: 2026-11-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_comunidad"
down_revision: Union[str, None] = "0005_conversaciones_wa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("espacios_comunes") as b:
        b.add_column(sa.Column("aforo", sa.Integer(), nullable=False, server_default="0"))
    with op.batch_alter_table("reservas_espacio") as b:
        b.add_column(sa.Column("asistentes", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "comunicados",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False, index=True),
        sa.Column("titulo", sa.String(160), nullable=False),
        sa.Column("cuerpo", sa.String(4000), nullable=False),
        sa.Column("categoria", sa.String(20), nullable=False, server_default="aviso"),
        sa.Column("fijado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("publicado_at", sa.DateTime(), nullable=False),
        sa.Column("vigente_hasta", sa.DateTime()),
        sa.Column("autor_id", sa.Integer(), sa.ForeignKey("residentes.id")),
    )
    op.create_table(
        "encomiendas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False, index=True),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=False, index=True),
        sa.Column("transportista", sa.String(60), nullable=False, server_default=""),
        sa.Column("remitente", sa.String(120), nullable=False, server_default=""),
        sa.Column("descripcion", sa.String(200), nullable=False, server_default=""),
        sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente", index=True),
        sa.Column("recibida_at", sa.DateTime(), nullable=False),
        sa.Column("recibida_por_id", sa.Integer(), sa.ForeignKey("residentes.id")),
        sa.Column("entregada_at", sa.DateTime()),
        sa.Column("entregada_por_id", sa.Integer(), sa.ForeignKey("residentes.id")),
        sa.Column("retirada_por", sa.String(120), nullable=False, server_default=""),
    )
    op.create_table(
        "avisos_pago",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False, index=True),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=False, index=True),
        sa.Column("residente_id", sa.Integer(), sa.ForeignKey("residentes.id")),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("banco", sa.String(60), nullable=False),
        sa.Column("nro_operacion", sa.String(40), nullable=False),
        sa.Column("fecha_transferencia", sa.Date(), nullable=False),
        sa.Column("estado", sa.String(12), nullable=False, server_default="pendiente", index=True),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.Column("resuelto_at", sa.DateTime()),
        sa.Column("motivo", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("edificio_id", "banco", "nro_operacion"),
    )


def downgrade() -> None:
    op.drop_table("avisos_pago")
    op.drop_table("encomiendas")
    op.drop_table("comunicados")
    with op.batch_alter_table("reservas_espacio") as b:
        b.drop_column("asistentes")
    with op.batch_alter_table("espacios_comunes") as b:
        b.drop_column("aforo")
