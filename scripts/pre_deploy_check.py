"""Verificador pre-despliegue: valida secretos, Docker Compose, migraciones Alembic y configuración."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    strict_prod = "--prod" in sys.argv or os.environ.get("ENTORNO") == "produccion"

    # 1. Escáner de secretos
    sec = subprocess.run([sys.executable, str(ROOT / "scripts/escaner_secretos.py")], cwd=ROOT)
    if sec.returncode != 0:
        print("ERROR: escaner_secretos.py detectó hallazgos.")
        return 1

    # 2. Validación de docker-compose.yml
    dc_env = os.environ.copy()
    if not strict_prod and not dc_env.get("DOMINIO"):
        dc_env["DOMINIO"] = "localhost.localdomain"
    dc = subprocess.run(["docker", "compose", "config", "-q"], cwd=ROOT, env=dc_env, capture_output=True, text=True)
    if dc.returncode != 0:
        print("ERROR: docker compose config falló:", dc.stderr)
        return 1

    # 3. Cabeza única de Alembic
    heads = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=ROOT / "backend",
        capture_output=True,
        text=True,
    )
    if heads.returncode != 0 or len([l for l in heads.stdout.splitlines() if l.strip()]) != 1:
        print("ERROR: Alembic no tiene una cabeza única:", heads.stdout, heads.stderr)
        return 1

    # 4. Controles estrictos de producción (si --prod o ENTORNO=produccion)
    if strict_prod:
        errores = []
        jwt_s = os.environ.get("JWT_SECRET", "")
        if len(jwt_s) < 32 or jwt_s.startswith("cambiar"):
            errores.append("JWT_SECRET debe tener >= 32 caracteres y no usar valor de ejemplo.")
        if not os.environ.get("MFA_ENCRYPTION_KEY"):
            errores.append("MFA_ENCRYPTION_KEY es obligatorio en producción.")
        if not os.environ.get("CORS_ORIGINS"):
            errores.append("CORS_ORIGINS es obligatorio en producción.")
        if not os.environ.get("DOMINIO"):
            errores.append("DOMINIO es obligatorio en producción.")
        if os.environ.get("DB_PASSWORD", "cambiar") == "cambiar":
            errores.append("DB_PASSWORD no puede ser 'cambiar'.")
        if not os.environ.get("DATABASE_URL", "").startswith("postgresql"):
            errores.append("DATABASE_URL debe apuntar a PostgreSQL en producción.")
        if errores:
            for e in errores:
                print("PRODUCCIÓN:", e)
            return 2

    print("pre_deploy_check OK (head:", heads.stdout.strip(), ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
