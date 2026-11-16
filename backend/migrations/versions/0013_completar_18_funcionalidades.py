"""completar 18 funcionalidades: torres, visitas recurrentes, adjuntos, garantias, push, encuestas

Revision ID: 0013_completar_18
Revises: 0012_contabilidad_ia
Create Date: 2026-11-16 20:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_completar_18"
down_revision: Union[str, None] = "0012_contabilidad_ia"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("unidades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("torre", sa.String(length=40), server_default="", nullable=False))

    with op.batch_alter_table("espacios_comunes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("garantia", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False))

    with op.batch_alter_table("reservas_espacio", schema=None) as batch_op:
        batch_op.add_column(sa.Column("garantia_estado", sa.String(length=20), server_default="", nullable=False))
        batch_op.add_column(sa.Column("penalizacion", sa.Numeric(precision=12, scale=2), server_default="0", nullable=False))

    with op.batch_alter_table("presupuestos_rubro", schema=None) as batch_op:
        batch_op.add_column(sa.Column("aprobado_asamblea_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_presupuesto_asamblea", "asambleas", ["aprobado_asamblea_id"], ["id"])

    op.create_table(
        "visitas_recurrentes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("unidad_id", sa.Integer(), nullable=False),
        sa.Column("nombre_visita", sa.String(length=120), nullable=False),
        sa.Column("patente", sa.String(length=12), nullable=False),
        sa.Column("dias_semana", sa.JSON(), nullable=False),
        sa.Column("hora_desde", sa.String(length=5), nullable=False),
        sa.Column("hora_hasta", sa.String(length=5), nullable=False),
        sa.Column("vigente_hasta", sa.Date(), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["unidad_id"], ["unidades.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("visitas_recurrentes", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_visitas_recurrentes_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_visitas_recurrentes_unidad_id"), ["unidad_id"], unique=False)

    op.create_table(
        "adjuntos_operacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("entidad", sa.String(length=20), nullable=False),
        sa.Column("entidad_id", sa.Integer(), nullable=False),
        sa.Column("nombre_archivo", sa.String(length=160), nullable=False),
        sa.Column("mime_type", sa.String(length=80), nullable=False),
        sa.Column("contenido_b64", sa.Text(), nullable=False),
        sa.Column("autorizado_por", sa.Integer(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["autorizado_por"], ["residentes.id"]),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("adjuntos_operacion", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_adjuntos_operacion_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_adjuntos_operacion_entidad"), ["entidad"], unique=False)
        batch_op.create_index(batch_op.f("ix_adjuntos_operacion_entidad_id"), ["entidad_id"], unique=False)

    op.create_table(
        "suscripciones_push",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("residente_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("p256dh", sa.String(length=200), nullable=False),
        sa.Column("auth", sa.String(length=100), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["residente_id"], ["residentes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("residente_id", "endpoint"),
    )
    with op.batch_alter_table("suscripciones_push", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_suscripciones_push_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_suscripciones_push_residente_id"), ["residente_id"], unique=False)

    op.create_table(
        "encuestas_comunidad",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("titulo", sa.String(length=160), nullable=False),
        sa.Column("pregunta", sa.String(length=400), nullable=False),
        sa.Column("activa", sa.Boolean(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("encuestas_comunidad", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_encuestas_comunidad_edificio_id"), ["edificio_id"], unique=False)

    op.create_table(
        "respuestas_encuesta",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("edificio_id", sa.String(length=40), nullable=False),
        sa.Column("encuesta_id", sa.Integer(), nullable=False),
        sa.Column("residente_id", sa.Integer(), nullable=False),
        sa.Column("puntaje", sa.Integer(), nullable=False),
        sa.Column("comentario", sa.String(length=400), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["edificio_id"], ["edificios.id"]),
        sa.ForeignKeyConstraint(["encuesta_id"], ["encuestas_comunidad.id"]),
        sa.ForeignKeyConstraint(["residente_id"], ["residentes.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("encuesta_id", "residente_id"),
    )
    with op.batch_alter_table("respuestas_encuesta", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_respuestas_encuesta_edificio_id"), ["edificio_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_respuestas_encuesta_encuesta_id"), ["encuesta_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("respuestas_encuesta", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_respuestas_encuesta_encuesta_id"))
        batch_op.drop_index(batch_op.f("ix_respuestas_encuesta_edificio_id"))
    op.drop_table("respuestas_encuesta")

    with op.batch_alter_table("encuestas_comunidad", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_encuestas_comunidad_edificio_id"))
    op.drop_table("encuestas_comunidad")

    with op.batch_alter_table("suscripciones_push", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_suscripciones_push_residente_id"))
        batch_op.drop_index(batch_op.f("ix_suscripciones_push_edificio_id"))
    op.drop_table("suscripciones_push")

    with op.batch_alter_table("adjuntos_operacion", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_adjuntos_operacion_entidad_id"))
        batch_op.drop_index(batch_op.f("ix_adjuntos_operacion_entidad"))
        batch_op.drop_index(batch_op.f("ix_adjuntos_operacion_edificio_id"))
    op.drop_table("adjuntos_operacion")

    with op.batch_alter_table("visitas_recurrentes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_visitas_recurrentes_unidad_id"))
        batch_op.drop_index(batch_op.f("ix_visitas_recurrentes_edificio_id"))
    op.drop_table("visitas_recurrentes")

    with op.batch_alter_table("presupuestos_rubro", schema=None) as batch_op:
        batch_op.drop_constraint("fk_presupuesto_asamblea", type_="foreignkey")
        batch_op.drop_column("aprobado_asamblea_id")

    with op.batch_alter_table("reservas_espacio", schema=None) as batch_op:
        batch_op.drop_column("penalizacion")
        batch_op.drop_column("garantia_estado")

    with op.batch_alter_table("espacios_comunes", schema=None) as batch_op:
        batch_op.drop_column("garantia")

    with op.batch_alter_table("unidades", schema=None) as batch_op:
        batch_op.drop_column("torre")
