#!/usr/bin/env bash
# ==============================================================================
# LaDock — Script Backup / Dump Database MySQL Sentral
# Mengambil dump database dari container ladock_mysql dengan datadir lokal
# dan menyimpannya secara rapi ke folder: mysql/db/<app_name>/
# ==============================================================================

set -euo pipefail
trap 'echo "❌ Terjadi kesalahan pada proses backup database di baris $LINENO!" >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$ROOT_DIR/.ladock_db.env"
CONFIG_FILE="$ROOT_DIR/config.json"

# Muat kredensial DB Sentral
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
Usage: $0 <app_name> [db_name] [output_dir]

Contoh:
  $0 campuscare
  $0 campuscare campuscare_db
  $0 campuscare campuscare_db /path/ke/folder
EOF
  exit 1
}

APP_NAME="${1:-}"
[[ -z "$APP_NAME" ]] && usage

# Normalisasi nama app
CLEAN_APP="$(echo "$APP_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
DB_NAME="${2:-${CLEAN_APP}_db}"
OUTPUT_DIR="${3:-$ROOT_DIR/mysql/db/$CLEAN_APP}"

mkdir -p "$OUTPUT_DIR"

echo "--> Memeriksa status container Database Sentral '$CONTAINER_NAME'..."
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "⚠️  Container '$CONTAINER_NAME' belum berjalan. Mencoba menjalankan..."
  "$SCRIPT_DIR/../central_db.sh" start
fi

# Cek apakah database ada
DB_EXISTS=$(docker exec -i "$CONTAINER_NAME" mysql -uroot -p"$ROOT_PASS" -e "SHOW DATABASES LIKE '$DB_NAME';" -sN 2>/dev/null || true)
if [[ -z "$DB_EXISTS" ]]; then
  echo "❌ Database '$DB_NAME' tidak ditemukan di container '$CONTAINER_NAME'!"
  exit 1
fi

TIMESTAMP="$(date +'%Y%m%d_%H%M%S')"
DATA_FILE="$OUTPUT_DIR/data.sql"
BACKUP_DIR="$OUTPUT_DIR/backups"
mkdir -p "$BACKUP_DIR"
BACKUP_ARCHIVE="$BACKUP_DIR/backup_${TIMESTAMP}.sql"
SCHEMA_FILE="$OUTPUT_DIR/schema.sql"

echo "--> Mengekspor database '$DB_NAME' dari volume Docker ke: $OUTPUT_DIR ..."

# 1. Export schema only
docker exec -i "$CONTAINER_NAME" mysqldump -uroot -p"$ROOT_PASS" \
  --no-data --routines --triggers "$DB_NAME" > "$SCHEMA_FILE" 2>/dev/null || true

# 2. Export full data
docker exec -i "$CONTAINER_NAME" mysqldump -uroot -p"$ROOT_PASS" \
  --routines --triggers "$DB_NAME" > "$DATA_FILE"

# 3. Salin juga ke arsip bertanggal di subfolder backups/
cp "$DATA_FILE" "$BACKUP_ARCHIVE"

# 4. Buat / update README.md di folder DB
cat > "$OUTPUT_DIR/README.md" <<EOF
# Database Info: ${APP_NAME}

- **Database Name**: \`${DB_NAME}\`
- **Host Container**: \`${CONTAINER_NAME}\` (datadir lokal: \`docker/ladock_mysql/data/\`)
- **Port Internal**: 3306
- **Port Host**: 3308
- **Last Backup**: $(date)
- **Files**:
  - \`schema.sql\` : Struktur tabel, routines, dan triggers
  - \`data.sql\`   : Dump lengkap data dan struktur terakhir
  - \`backup_${TIMESTAMP}.sql\` : Snapshot arsip saat backup dijalankan

### Cara Restore Manual:
\`\`\`bash
# Menggunakan helper script LaDock:
./scripts/db_restore.sh ${CLEAN_APP}

# Atau langsung via docker exec:
docker exec -i ${CONTAINER_NAME} mysql -uroot -p<ROOT_PASS> ${DB_NAME} < mysql/db/${CLEAN_APP}/data.sql
\`\`\`
EOF

echo "✓ Backup berhasil disimpan!"
echo "  - Schema   : $SCHEMA_FILE"
echo "  - Data     : $DATA_FILE"
echo "  - Arsip    : $BACKUP_ARCHIVE"
echo "  - Dokument : $OUTPUT_DIR/README.md"
