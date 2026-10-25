#!/usr/bin/env bash
# Restaura un respaldo en una base VACÍA y muestra cuántas filas trae, para comprobar que sirve.
#   scripts/restaurar_db.sh respaldos/edificios-AAAAMMDD-HHMMSS.dump postgresql://usuario:clave@host/base_vacia
# Por seguridad nunca restaura sobre la base en uso (DATABASE_URL) salvo que se pase --sobrescribir.
# Haga esta prueba al menos una vez antes de depender de los respaldos.
set -euo pipefail
SOBRE=0; ARGS=()
for a in "$@"; do [ "$a" = "--sobrescribir" ] && SOBRE=1 || ARGS+=("$a"); done
[ "${#ARGS[@]}" -eq 2 ] || { echo "Uso: $0 archivo.dump postgresql://destino [--sobrescribir]"; exit 1; }
ARCHIVO="${ARGS[0]}"; DEST="${ARGS[1]/postgresql+psycopg:/postgresql:}"
[ -f "$ARCHIVO" ] || { echo "No existe $ARCHIVO"; exit 1; }
ACTUAL="${DATABASE_URL:-}"; ACTUAL="${ACTUAL/postgresql+psycopg:/postgresql:}"
if [ "$SOBRE" -eq 0 ] && [ -n "$ACTUAL" ] && [ "$DEST" = "$ACTUAL" ]; then
  echo "El destino es la base en uso. Restaure en una base vacía, o repita con --sobrescribir si de verdad quiere reemplazarla."; exit 1
fi
pg_restore --no-owner --no-privileges --exit-on-error --dbname="$DEST" ${SOBRE:+--clean --if-exists} "$ARCHIVO"
echo "Restauración terminada. Filas por tabla:"
psql "$DEST" -At -c "select 'unidades', count(*) from unidades union all select 'residentes', count(*) from residentes union all select 'vehiculos', count(*) from vehiculos union all select 'tags', count(*) from tags union all select 'cargos', count(*) from cargos union all select 'pagos', count(*) from pagos;"
