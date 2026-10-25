#!/usr/bin/env bash
# Copia de seguridad de la base (PostgreSQL / Supabase) en formato comprimido de pg_dump.
#   DATABASE_URL=postgresql+psycopg://... scripts/respaldo_db.sh
# Variables: RESPALDO_DIR (por defecto ./respaldos), RESPALDO_DIAS (por defecto 14: borra copias más viejas).
# Programar a diario con cron, p. ej.:  15 3 * * *  cd /ruta/al/proyecto && scripts/respaldo_db.sh >> respaldos/respaldo.log 2>&1
# Nunca imprime la cadena de conexión (lleva la contraseña). Los archivos quedan con permiso 600.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -z "${DATABASE_URL:-}" ] && [ -f .env ]; then
  DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' .env | head -1)"
fi
[ -n "${DATABASE_URL:-}" ] || { echo "Falta DATABASE_URL (en el entorno o en .env)."; exit 1; }
URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"   # pg_dump no entiende el prefijo de SQLAlchemy
case "$URL" in postgresql:*|postgres:*) ;; *) echo "DATABASE_URL no es de PostgreSQL: este script no sirve para SQLite."; exit 1;; esac
command -v pg_dump >/dev/null || { echo "Falta pg_dump (instale postgresql-client)."; exit 1; }

DIR="${RESPALDO_DIR:-./respaldos}"; DIAS="${RESPALDO_DIAS:-14}"
mkdir -p "$DIR"; chmod 700 "$DIR"
ARCHIVO="$DIR/edificios-$(date +%Y%m%d-%H%M%S).dump"
umask 077
if ! pg_dump --format=custom --no-owner --no-privileges --dbname="$URL" --file="$ARCHIVO" 2>"$ARCHIVO.err"; then
  sed -E 's#(postgres(ql)?(\+[a-z]+)?://[^:/ ]+:)[^@ ]+@#\1****@#g' "$ARCHIVO.err" >&2
  rm -f "$ARCHIVO" "$ARCHIVO.err"; echo "El respaldo falló."; exit 1
fi
rm -f "$ARCHIVO.err"
pg_restore --list "$ARCHIVO" >/dev/null || { echo "El archivo generado no se puede leer: respaldo inválido."; rm -f "$ARCHIVO"; exit 1; }
find "$DIR" -name 'edificios-*.dump' -mtime "+$DIAS" -delete
echo "Respaldo listo: $ARCHIVO ($(du -h "$ARCHIVO" | cut -f1)). Se conservan $DIAS días."
