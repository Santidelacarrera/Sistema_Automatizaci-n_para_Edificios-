"""Las claves de lector (X-Device-Key) pasan a guardarse como hash SHA-256.

Revision ID: 0004_clave_dispositivo_hash
Revises: 0003_intentos_login
Create Date: 2026-10-24

Los lectores existentes siguen funcionando: el servidor compara el hash de lo que envían con
el hash guardado. La clave en claro ya no queda en la base ni en las copias de seguridad.
"""
import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_clave_dispositivo_hash"
down_revision: Union[str, None] = "0003_intentos_login"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    for eid, clave in conn.execute(sa.text("SELECT id, device_api_key FROM edificios")).fetchall():
        if len(clave) == 64 and all(c in "0123456789abcdef" for c in clave):
            continue  # ya es un hash (migración repetida)
        conn.execute(sa.text("UPDATE edificios SET device_api_key = :h WHERE id = :i"),
                     {"h": hashlib.sha256(clave.encode()).hexdigest(), "i": eid})


def downgrade() -> None:
    raise NotImplementedError("Un hash no se puede revertir: genere nuevas claves con rotar-clave.")
