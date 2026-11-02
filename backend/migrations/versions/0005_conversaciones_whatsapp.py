"""Conversaciones de WhatsApp en curso y mensajes ya procesados.

Revision ID: 0005_conversaciones_wa
Revises: 0004_clave_dispositivo_hash
Create Date: 2026-11-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_conversaciones_wa"
down_revision: Union[str, None] = "0004_clave_dispositivo_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversaciones_wa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telefono", sa.String(20), nullable=False, unique=True),
        sa.Column("estado", sa.String(20), nullable=False),
        sa.Column("datos", sa.JSON(), nullable=False),
        sa.Column("actualizado", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "mensajes_wa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("msg_id", sa.String(120), nullable=False, unique=True),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_mensajes_wa_creado", "mensajes_wa", ["creado"])


def downgrade() -> None:
    op.drop_table("mensajes_wa")
    op.drop_table("conversaciones_wa")
