"""Categoría explícita de cada cargo (desglose del estado de cuenta)

Revision ID: 0007_cargo_categoria
Revises: 0006_comunidad
Create Date: 2026-11-05

Los cargos existentes quedan con categoría vacía: el desglose los sigue deduciendo del concepto.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_cargo_categoria"
down_revision: Union[str, None] = "0006_comunidad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("cargos") as b:
        b.add_column(sa.Column("categoria", sa.String(20), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("cargos") as b:
        b.drop_column("categoria")
