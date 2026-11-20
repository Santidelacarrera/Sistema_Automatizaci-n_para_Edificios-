"""Crea tablas del motor Q&A hibrido y banco de memoria persistente.

Revision ID: 0016_motor_qa_memoria
Revises: 0015_obs_org_cotiz_regl
Create Date: 2026-11-20
"""
from alembic import op
import sqlalchemy as sa


revision = "0016_motor_qa_memoria"
down_revision = "0015_obs_org_cotiz_regl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fuentes_conocimiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("tipo_fuente", sa.String(40), nullable=False),
        sa.Column("referencia_id", sa.Integer(), nullable=False),
        sa.Column("titulo", sa.String(200), nullable=False),
        sa.Column("publico_comunidad", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=True),
        sa.Column("hash_contenido", sa.String(64), nullable=False),
        sa.Column("actualizado", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("edificio_id", "tipo_fuente", "referencia_id"),
    )
    op.create_index("ix_fuentes_conocimiento_edificio_id", "fuentes_conocimiento", ["edificio_id"])
    op.create_index("ix_fuentes_conocimiento_tipo_fuente", "fuentes_conocimiento", ["tipo_fuente"])
    op.create_index("ix_fuentes_conocimiento_unidad_id", "fuentes_conocimiento", ["unidad_id"])

    op.create_table(
        "fragmentos_conocimiento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fuente_id", sa.Integer(), sa.ForeignKey("fuentes_conocimiento.id", ondelete="CASCADE"), nullable=False),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=True),
        sa.Column("publico_comunidad", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("orden", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("seccion", sa.String(200), nullable=False, server_default="General"),
        sa.Column("tipo_bloque", sa.String(20), nullable=False, server_default="texto"),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("tokens_bm25", sa.JSON(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("metadatos_json", sa.JSON(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_fragmentos_conocimiento_fuente_id", "fragmentos_conocimiento", ["fuente_id"])
    op.create_index("ix_fragmentos_conocimiento_edificio_id", "fragmentos_conocimiento", ["edificio_id"])
    op.create_index("ix_fragmentos_conocimiento_unidad_id", "fragmentos_conocimiento", ["unidad_id"])

    op.create_table(
        "sesiones_memoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sesion_uuid", sa.String(64), nullable=False),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("residente_id", sa.Integer(), sa.ForeignKey("residentes.id"), nullable=False),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=True),
        sa.Column("entidades_activas", sa.JSON(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
        sa.Column("actualizado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_sesiones_memoria_sesion_uuid", "sesiones_memoria", ["sesion_uuid"], unique=True)
    op.create_index("ix_sesiones_memoria_edificio_id", "sesiones_memoria", ["edificio_id"])
    op.create_index("ix_sesiones_memoria_residente_id", "sesiones_memoria", ["residente_id"])

    op.create_table(
        "mensajes_memoria",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("sesion_id", sa.Integer(), sa.ForeignKey("sesiones_memoria.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("contenido", sa.Text(), nullable=False),
        sa.Column("metadatos_json", sa.JSON(), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_mensajes_memoria_sesion_id", "mensajes_memoria", ["sesion_id"])

    op.create_table(
        "memorias_episodicas",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("residente_id", sa.Integer(), sa.ForeignKey("residentes.id"), nullable=True),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=True),
        sa.Column("categoria", sa.String(50), nullable=False),
        sa.Column("clave_tema", sa.String(120), nullable=False),
        sa.Column("resumen", sa.Text(), nullable=False),
        sa.Column("hechos_clave_json", sa.JSON(), nullable=False),
        sa.Column("fuente_ref", sa.String(200), nullable=False, server_default=""),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("reemplaza_id", sa.Integer(), sa.ForeignKey("memorias_episodicas.id"), nullable=True),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_memorias_episodicas_edificio_id", "memorias_episodicas", ["edificio_id"])
    op.create_index("ix_memorias_episodicas_residente_id", "memorias_episodicas", ["residente_id"])
    op.create_index("ix_memorias_episodicas_unidad_id", "memorias_episodicas", ["unidad_id"])
    op.create_index("ix_memorias_episodicas_categoria", "memorias_episodicas", ["categoria"])
    op.create_index("ix_memorias_episodicas_clave_tema", "memorias_episodicas", ["clave_tema"])
    op.create_index("ix_memorias_episodicas_vigente", "memorias_episodicas", ["vigente"])

    op.create_table(
        "memorias_entidad",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("unidad_id", sa.Integer(), sa.ForeignKey("unidades.id"), nullable=True),
        sa.Column("entidad_tipo", sa.String(40), nullable=False),
        sa.Column("entidad_clave", sa.String(120), nullable=False),
        sa.Column("atributos_json", sa.JSON(), nullable=False),
        sa.Column("hechos_verificados", sa.JSON(), nullable=False),
        sa.Column("confianza", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("fuente_ref", sa.String(200), nullable=False, server_default=""),
        sa.Column("actualizado", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("edificio_id", "entidad_tipo", "entidad_clave"),
    )
    op.create_index("ix_memorias_entidad_edificio_id", "memorias_entidad", ["edificio_id"])
    op.create_index("ix_memorias_entidad_unidad_id", "memorias_entidad", ["unidad_id"])
    op.create_index("ix_memorias_entidad_entidad_tipo", "memorias_entidad", ["entidad_tipo"])

    op.create_table(
        "auditoria_consultas_ia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("edificio_id", sa.String(40), sa.ForeignKey("edificios.id"), nullable=False),
        sa.Column("residente_id", sa.Integer(), sa.ForeignKey("residentes.id"), nullable=False),
        sa.Column("rol", sa.String(20), nullable=False),
        sa.Column("pregunta_sanitizada", sa.Text(), nullable=False),
        sa.Column("variantes_consulta", sa.JSON(), nullable=False),
        sa.Column("filtros_alcance", sa.JSON(), nullable=False),
        sa.Column("fuentes_citadas", sa.JSON(), nullable=False),
        sa.Column("bloqueo_seguridad", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("modo_respuesta", sa.String(40), nullable=False),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auditoria_consultas_ia_edificio_id", "auditoria_consultas_ia", ["edificio_id"])
    op.create_index("ix_auditoria_consultas_ia_residente_id", "auditoria_consultas_ia", ["residente_id"])


def downgrade() -> None:
    op.drop_index("ix_auditoria_consultas_ia_residente_id", table_name="auditoria_consultas_ia")
    op.drop_index("ix_auditoria_consultas_ia_edificio_id", table_name="auditoria_consultas_ia")
    op.drop_table("auditoria_consultas_ia")
    op.drop_index("ix_memorias_entidad_entidad_tipo", table_name="memorias_entidad")
    op.drop_index("ix_memorias_entidad_unidad_id", table_name="memorias_entidad")
    op.drop_index("ix_memorias_entidad_edificio_id", table_name="memorias_entidad")
    op.drop_table("memorias_entidad")
    op.drop_index("ix_memorias_episodicas_vigente", table_name="memorias_episodicas")
    op.drop_index("ix_memorias_episodicas_clave_tema", table_name="memorias_episodicas")
    op.drop_index("ix_memorias_episodicas_categoria", table_name="memorias_episodicas")
    op.drop_index("ix_memorias_episodicas_unidad_id", table_name="memorias_episodicas")
    op.drop_index("ix_memorias_episodicas_residente_id", table_name="memorias_episodicas")
    op.drop_index("ix_memorias_episodicas_edificio_id", table_name="memorias_episodicas")
    op.drop_table("memorias_episodicas")
    op.drop_index("ix_mensajes_memoria_sesion_id", table_name="mensajes_memoria")
    op.drop_table("mensajes_memoria")
    op.drop_index("ix_sesiones_memoria_residente_id", table_name="sesiones_memoria")
    op.drop_index("ix_sesiones_memoria_edificio_id", table_name="sesiones_memoria")
    op.drop_index("ix_sesiones_memoria_sesion_uuid", table_name="sesiones_memoria")
    op.drop_table("sesiones_memoria")
    op.drop_index("ix_fragmentos_conocimiento_unidad_id", table_name="fragmentos_conocimiento")
    op.drop_index("ix_fragmentos_conocimiento_edificio_id", table_name="fragmentos_conocimiento")
    op.drop_index("ix_fragmentos_conocimiento_fuente_id", table_name="fragmentos_conocimiento")
    op.drop_table("fragmentos_conocimiento")
    op.drop_index("ix_fuentes_conocimiento_unidad_id", table_name="fuentes_conocimiento")
    op.drop_index("ix_fuentes_conocimiento_tipo_fuente", table_name="fuentes_conocimiento")
    op.drop_index("ix_fuentes_conocimiento_edificio_id", table_name="fuentes_conocimiento")
    op.drop_table("fuentes_conocimiento")
