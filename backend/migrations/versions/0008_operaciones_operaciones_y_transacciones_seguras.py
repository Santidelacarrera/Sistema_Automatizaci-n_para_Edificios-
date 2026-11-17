"""operaciones y transacciones seguras

Revision ID: 0008_operaciones
Revises: 0007_cargo_categoria
Create Date: 2026-11-16 17:27:34.725144

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008_operaciones'
down_revision: Union[str, None] = '0007_cargo_categoria'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('automatizaciones_config',
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('activa', sa.Boolean(), nullable=False),
    sa.Column('recordatorios_pago', sa.Boolean(), nullable=False),
    sa.Column('contratos_dias', sa.Integer(), nullable=False),
    sa.Column('max_notificaciones', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.PrimaryKeyConstraint('edificio_id')
    )
    op.create_table('proveedores',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('nombre', sa.String(length=120), nullable=False),
    sa.Column('rut', sa.String(length=15), nullable=False),
    sa.Column('contacto', sa.String(length=160), nullable=False),
    sa.Column('servicio', sa.String(length=160), nullable=False),
    sa.Column('contrato_hasta', sa.Date(), nullable=True),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('edificio_id', 'rut')
    )
    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_proveedores_edificio_id'), ['edificio_id'], unique=False)

    op.create_table('aplicaciones_pago',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('pago_id', sa.Integer(), nullable=False),
    sa.Column('cargo_id', sa.Integer(), nullable=False),
    sa.Column('monto', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.ForeignKeyConstraint(['cargo_id'], ['cargos.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['pago_id'], ['pagos.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('aplicaciones_pago', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_aplicaciones_pago_cargo_id'), ['cargo_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_pago_edificio_id'), ['edificio_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_aplicaciones_pago_pago_id'), ['pago_id'], unique=False)

    op.create_table('asambleas',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('titulo', sa.String(length=160), nullable=False),
    sa.Column('agenda', sa.Text(), nullable=False),
    sa.Column('fecha', sa.DateTime(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('opciones', sa.JSON(), nullable=False),
    sa.Column('acta', sa.Text(), nullable=False),
    sa.Column('creado_por', sa.Integer(), nullable=False),
    sa.Column('cerrada', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['creado_por'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('asambleas', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_asambleas_edificio_id'), ['edificio_id'], unique=False)

    op.create_table('documentos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('externo_id', sa.String(length=36), nullable=False),
    sa.Column('titulo', sa.String(length=160), nullable=False),
    sa.Column('categoria', sa.String(length=30), nullable=False),
    sa.Column('publico_comunidad', sa.Boolean(), nullable=False),
    sa.Column('vence', sa.Date(), nullable=True),
    sa.Column('creado_por', sa.Integer(), nullable=False),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['creado_por'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('edificio_id', 'externo_id')
    )
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_documentos_edificio_id'), ['edificio_id'], unique=False)

    op.create_table('incidencias',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('unidad_id', sa.Integer(), nullable=True),
    sa.Column('autor_id', sa.Integer(), nullable=False),
    sa.Column('titulo', sa.String(length=160), nullable=False),
    sa.Column('descripcion', sa.Text(), nullable=False),
    sa.Column('prioridad', sa.String(length=12), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('responsable_id', sa.Integer(), nullable=True),
    sa.Column('vencimiento', sa.Date(), nullable=True),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.Column('actualizado', sa.DateTime(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['autor_id'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['responsable_id'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_incidencias_edificio_id'), ['edificio_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_incidencias_estado'), ['estado'], unique=False)

    op.create_table('notificaciones',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('residente_id', sa.Integer(), nullable=False),
    sa.Column('clave', sa.String(length=120), nullable=False),
    sa.Column('canal', sa.String(length=12), nullable=False),
    sa.Column('titulo', sa.String(length=160), nullable=False),
    sa.Column('texto', sa.Text(), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('intentos', sa.Integer(), nullable=False),
    sa.Column('proximo_intento', sa.DateTime(), nullable=False),
    sa.Column('ultimo_error', sa.String(length=200), nullable=False),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.Column('leido', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['residente_id'], ['residentes.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('residente_id', 'clave', 'canal')
    )
    with op.batch_alter_table('notificaciones', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_notificaciones_edificio_id'), ['edificio_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_notificaciones_estado'), ['estado'], unique=False)
        batch_op.create_index(batch_op.f('ix_notificaciones_residente_id'), ['residente_id'], unique=False)

    op.create_table('comentarios_incidencia',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('incidencia_id', sa.Integer(), nullable=False),
    sa.Column('autor_id', sa.Integer(), nullable=False),
    sa.Column('texto', sa.Text(), nullable=False),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['autor_id'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['incidencia_id'], ['incidencias.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('comentarios_incidencia', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_comentarios_incidencia_edificio_id'), ['edificio_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_comentarios_incidencia_incidencia_id'), ['incidencia_id'], unique=False)

    op.create_table('ordenes_trabajo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('incidencia_id', sa.Integer(), nullable=False),
    sa.Column('proveedor_id', sa.Integer(), nullable=False),
    sa.Column('detalle', sa.Text(), nullable=False),
    sa.Column('presupuesto', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('estado', sa.String(length=20), nullable=False),
    sa.Column('aprobada_por', sa.Integer(), nullable=True),
    sa.Column('evaluacion', sa.Integer(), nullable=True),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['aprobada_por'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['incidencia_id'], ['incidencias.id'], ),
    sa.ForeignKeyConstraint(['proveedor_id'], ['proveedores.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('incidencia_id')
    )
    with op.batch_alter_table('ordenes_trabajo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_ordenes_trabajo_edificio_id'), ['edificio_id'], unique=False)

    op.create_table('participantes_asamblea',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('asamblea_id', sa.Integer(), nullable=False),
    sa.Column('unidad_id', sa.Integer(), nullable=False),
    sa.Column('residente_id', sa.Integer(), nullable=False),
    sa.Column('coeficiente', sa.Numeric(precision=9, scale=6), nullable=False),
    sa.Column('presente', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['asamblea_id'], ['asambleas.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['residente_id'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['unidad_id'], ['unidades.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('asamblea_id', 'residente_id'),
    sa.UniqueConstraint('asamblea_id', 'unidad_id')
    )
    with op.batch_alter_table('participantes_asamblea', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_participantes_asamblea_asamblea_id'), ['asamblea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_participantes_asamblea_edificio_id'), ['edificio_id'], unique=False)

    op.create_table('planes_mantenimiento',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('titulo', sa.String(length=160), nullable=False),
    sa.Column('responsable_id', sa.Integer(), nullable=False),
    sa.Column('intervalo_dias', sa.Integer(), nullable=False),
    sa.Column('proxima_fecha', sa.Date(), nullable=False),
    sa.Column('activo', sa.Boolean(), nullable=False),
    sa.Column('ultima_incidencia_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['responsable_id'], ['residentes.id'], ),
    sa.ForeignKeyConstraint(['ultima_incidencia_id'], ['incidencias.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('planes_mantenimiento', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_planes_mantenimiento_edificio_id'), ['edificio_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_planes_mantenimiento_proxima_fecha'), ['proxima_fecha'], unique=False)

    op.create_table('votos',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('edificio_id', sa.String(length=40), nullable=False),
    sa.Column('asamblea_id', sa.Integer(), nullable=False),
    sa.Column('participante_id', sa.Integer(), nullable=False),
    sa.Column('opcion', sa.Integer(), nullable=False),
    sa.Column('recibo', sa.String(length=64), nullable=False),
    sa.Column('creado', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['asamblea_id'], ['asambleas.id'], ),
    sa.ForeignKeyConstraint(['edificio_id'], ['edificios.id'], ),
    sa.ForeignKeyConstraint(['participante_id'], ['participantes_asamblea.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('participante_id'),
    sa.UniqueConstraint('recibo')
    )
    with op.batch_alter_table('votos', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_votos_asamblea_id'), ['asamblea_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_votos_edificio_id'), ['edificio_id'], unique=False)

    with op.batch_alter_table('edificios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('activo', sa.Boolean(), server_default='true', nullable=False))

    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.add_column(sa.Column('excedente', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('revertido', sa.Boolean(), server_default='false', nullable=False))
        batch_op.add_column(sa.Column('duplicado_de_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_pagos_duplicado', 'pagos', ['duplicado_de_id'], ['id'])

    with op.batch_alter_table('reservas_espacio', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cargo_id', sa.Integer(), nullable=True))
        batch_op.create_unique_constraint('uq_reserva_cargo', ['cargo_id'])
        batch_op.create_foreign_key('fk_reserva_cargo', 'cargos', ['cargo_id'], ['id'])

    with op.batch_alter_table('residentes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('session_version', sa.Integer(), server_default='0', nullable=False))

    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.add_column(sa.Column('saldo_favor', sa.Numeric(precision=14, scale=2), server_default='0', nullable=False))



def downgrade() -> None:
    with op.batch_alter_table('unidades', schema=None) as batch_op:
        batch_op.drop_column('saldo_favor')

    with op.batch_alter_table('residentes', schema=None) as batch_op:
        batch_op.drop_column('session_version')

    with op.batch_alter_table('reservas_espacio', schema=None) as batch_op:
        batch_op.drop_constraint('fk_reserva_cargo', type_='foreignkey')
        batch_op.drop_constraint('uq_reserva_cargo', type_='unique')
        batch_op.drop_column('cargo_id')

    with op.batch_alter_table('pagos', schema=None) as batch_op:
        batch_op.drop_constraint('fk_pagos_duplicado', type_='foreignkey')
        batch_op.drop_column('duplicado_de_id')
        batch_op.drop_column('revertido')
        batch_op.drop_column('excedente')

    with op.batch_alter_table('edificios', schema=None) as batch_op:
        batch_op.drop_column('activo')

    with op.batch_alter_table('votos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_votos_edificio_id'))
        batch_op.drop_index(batch_op.f('ix_votos_asamblea_id'))

    op.drop_table('votos')
    with op.batch_alter_table('planes_mantenimiento', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_planes_mantenimiento_proxima_fecha'))
        batch_op.drop_index(batch_op.f('ix_planes_mantenimiento_edificio_id'))

    op.drop_table('planes_mantenimiento')
    with op.batch_alter_table('participantes_asamblea', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_participantes_asamblea_edificio_id'))
        batch_op.drop_index(batch_op.f('ix_participantes_asamblea_asamblea_id'))

    op.drop_table('participantes_asamblea')
    with op.batch_alter_table('ordenes_trabajo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_ordenes_trabajo_edificio_id'))

    op.drop_table('ordenes_trabajo')
    with op.batch_alter_table('comentarios_incidencia', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_comentarios_incidencia_incidencia_id'))
        batch_op.drop_index(batch_op.f('ix_comentarios_incidencia_edificio_id'))

    op.drop_table('comentarios_incidencia')
    with op.batch_alter_table('notificaciones', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_notificaciones_residente_id'))
        batch_op.drop_index(batch_op.f('ix_notificaciones_estado'))
        batch_op.drop_index(batch_op.f('ix_notificaciones_edificio_id'))

    op.drop_table('notificaciones')
    with op.batch_alter_table('incidencias', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_incidencias_estado'))
        batch_op.drop_index(batch_op.f('ix_incidencias_edificio_id'))

    op.drop_table('incidencias')
    with op.batch_alter_table('documentos', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_documentos_edificio_id'))

    op.drop_table('documentos')
    with op.batch_alter_table('asambleas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_asambleas_edificio_id'))

    op.drop_table('asambleas')
    with op.batch_alter_table('aplicaciones_pago', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_aplicaciones_pago_pago_id'))
        batch_op.drop_index(batch_op.f('ix_aplicaciones_pago_edificio_id'))
        batch_op.drop_index(batch_op.f('ix_aplicaciones_pago_cargo_id'))

    op.drop_table('aplicaciones_pago')
    with op.batch_alter_table('proveedores', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_proveedores_edificio_id'))

    op.drop_table('proveedores')
    op.drop_table('automatizaciones_config')
