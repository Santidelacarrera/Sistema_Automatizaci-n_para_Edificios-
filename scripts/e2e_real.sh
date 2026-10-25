#!/usr/bin/env bash
# E2E del panel contra el backend real con datos sembrados (SQLite temporal, sin servicios externos).
# Uso: scripts/e2e_real.sh            (usa PW_CHROMIUM=/ruta/chromium si no hay Chrome instalado)
set -euo pipefail
RAIZ="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
PY="${PYTHON:-python3}"
export DATABASE_URL="sqlite:///$TMP/e2e.db" ENTORNO=desarrollo
export JWT_SECRET="$($PY -c 'import secrets;print(secrets.token_urlsafe(48))')"
export E2E_API="http://localhost:8000" E2E_EDIFICIO="e2e_a" E2E_EMAIL="admin@e2e.cl"
export E2E_PASSWORD="$($PY -c 'import secrets;print(secrets.token_urlsafe(18))')"
for puerto in 3000 8000; do
  if (exec 3<>/dev/tcp/127.0.0.1/$puerto) 2>/dev/null; then
    echo "El puerto $puerto ya está en uso: cierre ese proceso antes de correr el E2E."; exit 1
  fi
done
PIDS=()
# se mata el grupo entero porque npx deja procesos hijos
limpiar() { for p in "${PIDS[@]:-}"; do kill -- "-$p" 2>/dev/null || kill "$p" 2>/dev/null || true; done; rm -rf "$TMP"; }
trap limpiar EXIT

cd "$RAIZ/backend"
alembic upgrade head >/dev/null
SALIDA="$(SEED_ADMIN_PASSWORD="$E2E_PASSWORD" $PY scripts/seed.py --id e2e_a --nombre "Edificio E2E" \
  --departamentos 101,102,103,201,202,203 --admin-nombre "Admin E2E" --admin-rut 11111111-1 \
  --admin-email "$E2E_EMAIL" --admin-unidad 101)"
export E2E_DEVICE_KEY="$(echo "$SALIDA" | sed -n 's/^X-Device-Key[^:]*: //p' | head -1)"
[ -n "$E2E_DEVICE_KEY" ] || { echo "No se pudo leer la clave de dispositivo del seed"; exit 1; }
# estacionamientos para poder registrar vehículos
$PY - <<PYEOF
from app.db import SessionLocal
from app.models import EspacioComun, Regla, Unidad
with SessionLocal() as db:
    for u in db.query(Unidad).filter_by(edificio_id="e2e_a"):
        u.estacionamientos = 2
    db.add(EspacioComun(edificio_id="e2e_a", nombre="Quincho", accion="reservar_quincho", tarifa=5000))
    db.add(Regla(edificio_id="e2e_a", accion="reservar_quincho", tipo="horario", params={"desde": "10:00", "hasta": "22:00"}))
    db.commit()
PYEOF

CORS_ORIGINS="http://localhost:3000" setsid uvicorn app.main:app --port 8000 >"$TMP/api.log" 2>&1 & PIDS+=($!)
cd "$RAIZ/frontend"
NEXT_PUBLIC_API_URL="$E2E_API" npx next build >"$TMP/build.log" 2>&1 || { tail -30 "$TMP/build.log"; exit 1; }
setsid npx next start -p 3000 >"$TMP/web.log" 2>&1 & PIDS+=($!)
for i in $(seq 1 60); do curl -fs localhost:8000/health >/dev/null && curl -fs localhost:3000 >/dev/null && break; sleep 1; done
PW_BASE_URL="http://localhost:3000" npx playwright test -c playwright.real.config.js
