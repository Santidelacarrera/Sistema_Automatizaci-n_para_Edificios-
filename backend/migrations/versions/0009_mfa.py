"""Segundo factor cifrado, bloqueo y protección contra reutilización de códigos."""
from alembic import op
import sqlalchemy as sa

revision = "0009_mfa"
down_revision = "0008_operaciones"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("segundos_factores",
        sa.Column("residente_id", sa.Integer(), sa.ForeignKey("residentes.id"), primary_key=True),
        sa.Column("secreto_cifrado", sa.String(500), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("ultimo_paso", sa.Integer(), nullable=False),
        sa.Column("intentos", sa.Integer(), nullable=False),
        sa.Column("bloqueado_hasta", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_table("segundos_factores")
