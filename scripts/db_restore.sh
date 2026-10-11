#!/usr/bin/env bash
# ==============================================================================
# LaDock — Script Restore Database MySQL Sentral
# Mengimpor dump SQL dari folder mysql/db/<app_name>/ ke dalam Docker Named Volume
# (melalui container ladock_mysql)
# ==============================================================================

set -euo pipefail
trap 'echo "❌ Terjadi kesalahan pada proses restore database di baris $LINENO!" >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.ladock_db.env"

CONTAINER_NAME="ladock_mysql"
ROOT_PASS="3baa6e5d124af02611fd0efb79ae292d"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  CONTAINER_NAME="${LADOCK_DB_CONTAINER:-$CONTAINER_NAME}"
  ROOT_PASS="${LADOCK_DB_ROOT_PASS:-$ROOT_PASS}"
fi

usage() {
  cat <<EOF
Usage: $0 <app_name> [path_to_sql_file] [db_name]

Contoh:
  $0 campuscare
  $0 campuscare /path/ke/custom_backup.sql
  $0 campuscare mysql/db/campuscare/data.sql custom_db_name
EOF
  exit 1
}

APP_NAME="${1:-}"
[[ -z "$APP_NAME" ]] && usage

CLEAN_APP="$(echo "$APP_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
SQL_FILE="${2:-$ROOT_DIR/mysql/db/$CLEAN_APP/data.sql}"
DB_NAME="${3:-${CLEAN_APP}_db}"

if [[ ! -f "$SQL_FILE" ]]; then
  # Cek jika ada file .sql lain di direktori DB
  if [[ -d "$ROOT_DIR/mysql/db/$CLEAN_APP" ]]; then
    FOUND_SQL=$(find "$ROOT_DIR/mysql/db/$CLEAN_APP" -maxdepth 1 -name "*.sql" | head -n1 || true)
    if [[ -n "$FOUND_SQL" && -f "$FOUND_SQL" ]]; then
      SQL_FILE="$FOUND_SQL"
    fi
  fi
fi

if [[ ! -f "$SQL_FILE" ]]; then
  echo "❌ File dump database tidak ditemukan: $SQL_FILE"
  exit 1
fi

echo "--> Memeriksa status container Database Sentral '$CONTAINER_NAME'..."
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "⚠️  Container '$CONTAINER_NAME' belum berjalan. Menjalankan..."
  "$SCRIPT_DIR/../central_db.sh" start
fi

echo "--> Memastikan database target '$DB_NAME' siap di container '$CONTAINER_NAME'..."
docker exec -i "$CONTAINER_NAME" mysql -uroot -p"$ROOT_PASS" -e "
  CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
" >/dev/null 2>&1

echo "--> Mengimpor dump '$SQL_FILE' ke database '$DB_NAME'..."
# Filter perintah CREATE DATABASE / DROP DATABASE agar tidak menimpa database lain
docker exec -i "$CONTAINER_NAME" bash -c "
  sed -E 's/^(CREATE|DROP) DATABASE .*;//gi' | mysql -uroot -p'$ROOT_PASS' '$DB_NAME'
" < "$SQL_FILE"

TABLE_COUNT=$(docker exec -i "$CONTAINER_NAME" mysql -uroot -p"$ROOT_PASS" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" -sN 2>/dev/null || echo "0")

echo "✓ Restore selesai! Database '$DB_NAME' sekarang memiliki $TABLE_COUNT tabel."
