#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Laravel Docker Auto-Deploy (Apache + Auto-Detect PHP + Auto-Import DB + Seeder)
#  Usage: ./deploy.sh /path/to/laravel-project [http_port] [db_port] [php_version] [flags]
#
#  Flags (opsional, bisa diletakkan di mana saja):
#    --dump=/path/file.sql   Path eksplisit file dump database yang mau diimport
#    --force-import          Paksa import dump walau ini bukan deploy pertama
#    --skip-import           Jangan pernah import dump (walau deploy pertama)
#    --force-seed            Paksa jalankan php artisan db:seed walau redeploy
#    --skip-seed             Jangan jalankan seeder sama sekali
#
#  Kalau php_version tidak diberikan, akan dideteksi dari composer.json.
#  Kalau project_path tidak diberikan, akan dicari otomatis di folder saat ini.
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

# --- Pisahkan flag (--xxx) dari argumen posisional (kompatibel dgn versi lama) ---
ARGS=()
DUMP_FILE=""
FORCE_IMPORT=0
SKIP_IMPORT=0
FORCE_SEED=0
SKIP_SEED=0
for arg in "$@"; do
  case "$arg" in
    --dump=*)       DUMP_FILE="${arg#--dump=}" ;;
    --force-import) FORCE_IMPORT=1 ;;
    --skip-import)  SKIP_IMPORT=1 ;;
    --force-seed)   FORCE_SEED=1 ;;
    --skip-seed)    SKIP_SEED=1 ;;
    *) ARGS+=("$arg") ;;
  esac
done

PROJECT_PATH="${ARGS[0]:-}"
HTTP_PORT="${ARGS[1]:-8080}"
DB_PORT="${ARGS[2]:-3307}"
PHP_VERSION_PARAM="${ARGS[3]:-}"

usage() {
  echo "Usage: $0 /path/to/laravel-project [http_port] [db_port] [php_version] [flags]"
  echo "  php_version : 5.6, 7.0, 7.1, 7.2, 7.3, 7.4, 8.0, 8.1, 8.2, 8.3, 8.4 (default auto-detect)"
  echo "  --dump=FILE    : path eksplisit file dump .sql yang mau diimport"
  echo "  --force-import : paksa import dump walau redeploy"
  echo "  --skip-import  : jangan import dump sama sekali"
  echo "  --force-seed   : paksa jalankan php artisan db:seed walau redeploy"
  echo "  --skip-seed    : jangan jalankan seeder sama sekali"
}

# --- python3 wajib ada (dipakai untuk deteksi PHP, cari project, import DB) ---
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 tidak ditemukan. Install python3 terlebih dahulu (dipakai untuk deteksi PHP version, cari project, dan import database)."
  exit 1
fi

# --- Kalau project path tidak diisi, coba cari otomatis pakai python ---
if [[ -z "$PROJECT_PATH" ]]; then
  echo "-> Project path tidak diisi, mencari project Laravel di folder ini ($(pwd))..."
  mapfile -t FOUND < <(python3 "$SCRIPTS_DIR/find_laravel_projects.py" "$(pwd)")
  if [[ ${#FOUND[@]} -eq 0 ]]; then
    echo "Tidak ditemukan project Laravel di bawah $(pwd)."
    usage
    exit 1
  elif [[ ${#FOUND[@]} -eq 1 ]]; then
    PROJECT_PATH="${FOUND[0]}"
    echo "-> Ditemukan 1 project: $PROJECT_PATH"
  else
    echo "Ditemukan beberapa project Laravel, pilih salah satu:"
    select p in "${FOUND[@]}"; do
      if [[ -n "$p" ]]; then
        PROJECT_PATH="$p"
        break
      fi
    done
  fi
fi

if [[ -z "$PROJECT_PATH" ]]; then
  usage
  exit 1
fi

if [[ ! -d "$PROJECT_PATH" ]]; then
  echo "Folder tidak ditemukan: $PROJECT_PATH"
  exit 1
fi

PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"

# --- Validasi project Laravel ---
if [[ ! -f "$PROJECT_PATH/artisan" ]]; then
  echo "Folder '$PROJECT_PATH' bukan project Laravel yang valid (file 'artisan' tidak ditemukan)."
  exit 1
fi

RAW_NAME="$(basename "$PROJECT_PATH")"
PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"

# --- Tentukan PHP_VERSION (via python, lebih akurat daripada grep/sed) ---
if [[ -z "$PHP_VERSION_PARAM" ]]; then
  PHP_VERSION=$(python3 "$SCRIPTS_DIR/detect_php_version.py" "$PROJECT_PATH/composer.json")
  echo "-> Deteksi otomatis PHP version: $PHP_VERSION (dari composer.json, via python)"
else
  PHP_VERSION="$PHP_VERSION_PARAM"
fi

# --- Tentukan Composer version ---
if [[ "$(printf '%s\n' "$PHP_VERSION" "7.2" | sort -V | head -n1)" == "$PHP_VERSION" && "$PHP_VERSION" != "7.2" ]]; then
  COMPOSER_VERSION=1
else
  COMPOSER_VERSION=2
fi

echo "=============================================="
echo " Project      : $PROJECT_NAME"
echo " Path         : $PROJECT_PATH"
echo " Web Server   : Apache"
echo " HTTP Port    : $HTTP_PORT"
echo " MySQL Port   : $DB_PORT"
echo " PHP Version  : $PHP_VERSION"
echo " Composer Ver : $COMPOSER_VERSION"
echo "=============================================="

DOCKER_DIR="$PROJECT_PATH/.docker"
CREDS_FILE="$DOCKER_DIR/credentials.env"
COMPOSE_FILE="$PROJECT_PATH/.docker-compose.yml"

mkdir -p "$DOCKER_DIR"

# --- Deteksi compose command ---
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "Docker Compose tidak ditemukan. Install Docker Desktop / docker-compose-plugin terlebih dahulu."
  exit 1
fi

# --- Kredensial DB (idempotent) ---
FRESH_DEPLOY=0
if [[ -f "$CREDS_FILE" ]]; then
  echo "-> Menggunakan kredensial database yang sudah ada..."
  # shellcheck disable=SC1090
  source "$CREDS_FILE"
else
  echo "-> Membuat kredensial database baru..."
  FRESH_DEPLOY=1
  DB_NAME="${PROJECT_NAME}_db"
  SHORT_NAME="$(echo "$PROJECT_NAME" | cut -c1-20)"
  DB_USER="${SHORT_NAME}_user"
  DB_PASS="$(openssl rand -hex 12)"
  DB_ROOT_PASS="$(openssl rand -hex 12)"
  cat > "$CREDS_FILE" <<EOF
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS
DB_ROOT_PASS=$DB_ROOT_PASS
EOF
fi

# --- Siapkan file konfigurasi dari template ---
echo "-> Menyiapkan file Docker (Dockerfile, apache-vhost.conf, docker-compose.yml)..."
cp "$TEMPLATE_DIR/Dockerfile" "$DOCKER_DIR/Dockerfile"

sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
    "$TEMPLATE_DIR/apache-vhost.conf.tpl" > "$DOCKER_DIR/apache-vhost.conf"

sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
    -e "s/__HTTP_PORT__/$HTTP_PORT/g" \
    -e "s/__DB_PORT__/$DB_PORT/g" \
    -e "s/__DB_NAME__/$DB_NAME/g" \
    -e "s/__DB_USER__/$DB_USER/g" \
    -e "s/__DB_PASS__/$DB_PASS/g" \
    -e "s/__DB_ROOT_PASS__/$DB_ROOT_PASS/g" \
    -e "s/__PHP_VERSION__/$PHP_VERSION/g" \
    -e "s/__COMPOSER_VERSION__/$COMPOSER_VERSION/g" \
    "$TEMPLATE_DIR/docker-compose.yml.tpl" > "$COMPOSE_FILE"

# --- Siapkan .env Laravel ---
cd "$PROJECT_PATH"
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "-> .env dibuat dari .env.example"
  else
    touch .env
  fi
fi

set_env () {
  local key="$1" val="$2"
  if grep -q "^${key}=" .env; then
    sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
  else
    echo "${key}=${val}" >> .env
  fi
}

set_env "DB_CONNECTION" "mysql"
set_env "DB_HOST" "db_${PROJECT_NAME}"
set_env "DB_PORT" "3306"
set_env "DB_DATABASE" "$DB_NAME"
set_env "DB_USERNAME" "$DB_USER"
set_env "DB_PASSWORD" "$DB_PASS"

# --- Bersihkan container lama ---
echo "-> Membersihkan container lama project ini (jika ada)..."
$DC -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true

# --- Build & up ---
echo "-> Build image & menjalankan container..."
$DC -f "$COMPOSE_FILE" -p "$PROJECT_NAME" up -d --build

# --- Tunggu MySQL siap ---
echo "-> Menunggu MySQL siap (hingga 60 detik)..."
timeout=60
elapsed=0
until $DC -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T "db_${PROJECT_NAME}" \
      mysql -uroot -p"$DB_ROOT_PASS" -e "SELECT 1" >/dev/null 2>&1; do
  if [[ $elapsed -ge $timeout ]]; then
    echo "MySQL tidak siap setelah $timeout detik. Keluar."
    exit 1
  fi
  sleep 2
  elapsed=$((elapsed+2))
  echo "   ... menunggu ($elapsed/${timeout}s)"
done
echo "MySQL siap!"

# --- Import dump database (.sql) kalau relevan ---
# Dijalankan SEBELUM migrate, supaya migrate cuma menambah migration baru
# yang belum ada di dalam dump (bukan bentrok sama tabel yang baru dibuat).
# Default: hanya jalan otomatis di deploy PERTAMA kali (biar redeploy tidak
# menimpa data yang sudah dipakai/berubah), kecuali --force-import atau --dump dipakai.
SHOULD_IMPORT=0
if [[ $SKIP_IMPORT -eq 0 ]]; then
  if [[ $FRESH_DEPLOY -eq 1 || $FORCE_IMPORT -eq 1 || -n "$DUMP_FILE" ]]; then
    SHOULD_IMPORT=1
  fi
fi

if [[ $SHOULD_IMPORT -eq 1 ]]; then
  echo "-> Mencari & mengimpor dump database (.sql) jika ada..."
  python3 "$SCRIPTS_DIR/db_import.py" \
    --project-path "$PROJECT_PATH" \
    --project-name "$PROJECT_NAME" \
    --compose-file "$COMPOSE_FILE" \
    --db-name "$DB_NAME" \
    --db-root-pass "$DB_ROOT_PASS" \
    --dc "$DC" \
    ${DUMP_FILE:+--dump "$DUMP_FILE"}
else
  echo "-> Lewati import dump (bukan deploy pertama; pakai --force-import kalau mau paksa import ulang)."
fi

# --- Tentukan apakah seeder perlu dijalankan ---
# Default: hanya jalan otomatis di deploy PERTAMA kali (biar redeploy tidak
# menimpa data yang sudah dipakai/berubah), kecuali --force-seed dipakai.
SHOULD_SEED=0
if [[ $SKIP_SEED -eq 0 ]]; then
  if [[ $FRESH_DEPLOY -eq 1 || $FORCE_SEED -eq 1 ]]; then
    SHOULD_SEED=1
  fi
fi

if [[ $SHOULD_SEED -eq 1 ]]; then
  SEED_CMD="php artisan db:seed --force || true"
  echo "-> Seeder akan dijalankan setelah migrate."
else
  SEED_CMD="echo '-> Lewati db:seed (bukan deploy pertama; pakai --force-seed kalau mau paksa seed ulang).'"
fi

# --- Setup Laravel (dengan fallback composer update) ---
echo "-> Menjalankan composer install, migrate & seed di dalam container..."
$DC -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T "app_${PROJECT_NAME}" bash -lc "
  # Coba composer install, jika gagal karena PHP version, jalankan composer update
  if composer install --no-interaction --prefer-dist --optimize-autoloader 2>&1 | tee /tmp/composer_output | grep -q 'does not satisfy'; then
    echo '⚠️  Dependencies tidak kompatibel dengan PHP $PHP_VERSION, menjalankan composer update...'
    composer update --no-interaction --prefer-dist --optimize-autoloader
  fi
  php artisan key:generate --force || true
  php artisan config:clear || true
  php artisan migrate --force || true
  $SEED_CMD
  php artisan storage:link || true
"

echo ""
echo "=============================================="
echo " SELESAI - Laravel project '$PROJECT_NAME' sudah live"
echo " Akses Web   : http://localhost:$HTTP_PORT"
echo " MySQL       : localhost:$DB_PORT"
echo "   DB Name   : $DB_NAME"
echo "   DB User   : $DB_USER"
echo "   DB Pass   : $DB_PASS"
echo "   DB Root   : $DB_ROOT_PASS"
echo " PHP Versi   : $PHP_VERSION"
echo " Kredensial tersimpan di: $CREDS_FILE"
echo "=============================================="