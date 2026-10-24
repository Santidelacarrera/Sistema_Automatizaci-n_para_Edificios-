"""Intentos de inicio de sesión (bloqueo temporal por fuerza bruta).

Revision ID: 0003_intentos_login
Revises: 0002_stickers
Create Date: 2026-10-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_intentos_login"
down_revision: Union[str, None] = "0002_stickers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "intentos_login",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("clave", sa.String(220), nullable=False),
        sa.Column("ip", sa.String(64), nullable=False, server_default=""),
        sa.Column("exitoso", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("creado", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_intentos_login_clave", "intentos_login", ["clave"])
    op.create_index("ix_intentos_login_ip", "intentos_login", ["ip"])
    op.create_index("ix_intentos_login_creado", "intentos_login", ["creado"])


def downgrade() -> None:
    op.drop_table("intentos_login")
