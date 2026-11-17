"""Agrega errores_log, organizaciones, miembros_organizacion, cotizaciones_proveedor y reglamentos_internos.

Revision ID: 0015_obs_org_cotiz_regl
Revises: 0014_reservas_porteria_pisos
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa


revision = "0015_obs_org_cotiz_regl"
down_revision = "0014_reservas_porteria_pisos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "errores_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ruta", sa.String(200), nullable=False),
        sa.Column("metodo", sa.String(12), nullable=False),
        sa.Column("edificio_id", sa.String(40), nullable=False, server_default=""),
        sa.Column("mensaje", sa.String(300), nullable=False),
        sa.Column("detalle", sa.Text(), nullable=False, server_default=""),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "organizaciones",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_organizaciones_slug", "organizaciones", ["slug"], unique=True)

    op.create_table(
        "miembros_organizacion",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organizacion_id", sa.Integer(), sa.ForeignKey("organizaciones.id"), nullable=False),
        sa.Column("email", sa.String(160), nullable=False),
        sa.Column("rol", sa.String(30), nullable=False, server_default="gestor"),
        sa.Column("activo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("organizacion_id", "email"),
    )
    op.create_index("ix_miembros_organizacion_organizacion_id", "miembros_organizacion", ["organizacion_id"])

    op.create_table(
        "cotizaciones_proveedor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("incidencia_id", sa.Integer(), sa.ForeignKey("incidencias.id"), nullable=False),
        sa.Column("proveedor_id", sa.Integer(), sa.ForeignKey("proveedores.id"), nullable=False),
        sa.Column("monto", sa.Numeric(14, 2), nullable=False),
        sa.Column("plazo_dias", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("detalle", sa.String(400), nullable=False, server_default=""),
        sa.Column("estado", sa.String(20), nullable=False, server_default="pendiente"),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_cotizaciones_proveedor_edificio_id", "cotizaciones_proveedor", ["edificio_id"])
    op.create_index("ix_cotizaciones_proveedor_incidencia_id", "cotizaciones_proveedor", ["incidencia_id"])

    op.create_table(
        "reglamentos_internos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("titulo", sa.String(160), nullable=False),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("creado_por", sa.Integer(), sa.ForeignKey("residentes.id"), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_reglamentos_internos_edificio_id", "reglamentos_internos", ["edificio_id"])


def downgrade() -> None:
    op.drop_index("ix_reglamentos_internos_edificio_id", table_name="reglamentos_internos")
    op.drop_table("reglamentos_internos")
    op.drop_index("ix_cotizaciones_proveedor_incidencia_id", table_name="cotizaciones_proveedor")
    op.drop_index("ix_cotizaciones_proveedor_edificio_id", table_name="cotizaciones_proveedor")
    op.drop_table("cotizaciones_proveedor")
    op.drop_index("ix_miembros_organizacion_organizacion_id", table_name="miembros_organizacion")
    op.drop_table("miembros_organizacion")
    op.drop_index("ix_organizaciones_slug", table_name="organizaciones")
    op.drop_table("organizaciones")
    op.drop_table("errores_log")
