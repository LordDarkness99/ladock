#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Laravel Docker Auto-Deploy (Dengan Auto-Detect PHP)
#  Usage: ./deploy.sh /path/to/laravel-project [http_port] [db_port] [php_version]
#  Jika php_version tidak diberikan, akan dideteksi dari composer.json
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"

PROJECT_PATH="${1:-}"
HTTP_PORT="${2:-8080}"
DB_PORT="${3:-3307}"
PHP_VERSION_PARAM="${4:-}"  # opsional

if [[ -z "$PROJECT_PATH" ]]; then
  echo "Usage: $0 /path/to/laravel-project [http_port] [db_port] [php_version]"
  echo "  php_version: 5.6, 7.0, 7.1, 7.2, 7.3, 7.4, 8.0, 8.1, 8.2, 8.3, 8.4 (default auto-detect)"
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

# --- Fungsi deteksi PHP version dari composer.json ---
detect_php_version() {
  local composer_file="$1/composer.json"
  if [[ ! -f "$composer_file" ]]; then
    echo "8.4"
    return
  fi

  local constraint=$(grep -E '"php"[[:space:]]*:' "$composer_file" | sed -E 's/.*"php"[[:space:]]*:[[:space:]]*"([^"]+)".*/\1/' | head -1)
  
  if [[ -z "$constraint" ]]; then
    echo "8.4"
    return
  fi

  case "$constraint" in
    *"5.6"*)   echo "5.6" ;;
    *"7.0"*)   echo "7.0" ;;
    *"7.1"*)   echo "7.1" ;;
    *"7.2"*)   echo "7.2" ;;
    *"7.3"*)   echo "7.3" ;;
    *"7.4"*)   echo "7.4" ;;
    *"8.0"*)   echo "8.0" ;;
    *"8.1"*)   echo "8.1" ;;
    *"8.2"*)   echo "8.2" ;;
    *"8.3"*)   echo "8.3" ;;
    *"8.4"*)   echo "8.4" ;;
    *)
      if [[ "$constraint" =~ ">=7" ]] && [[ ! "$constraint" =~ "8" ]]; then
        echo "7.4"
      elif [[ "$constraint" =~ ">=8" ]]; then
        echo "8.4"
      elif [[ "$constraint" =~ ">=5" ]]; then
        echo "5.6"
      else
        echo "8.4"
      fi
      ;;
  esac
}

# --- Tentukan PHP_VERSION ---
if [[ -z "$PHP_VERSION_PARAM" ]]; then
  PHP_VERSION=$(detect_php_version "$PROJECT_PATH")
  echo "-> Deteksi otomatis PHP version: $PHP_VERSION (dari composer.json)"
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
if [[ -f "$CREDS_FILE" ]]; then
  echo "-> Menggunakan kredensial database yang sudah ada..."
  # shellcheck disable=SC1090
  source "$CREDS_FILE"
else
  echo "-> Membuat kredensial database baru..."
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
echo "-> Menyiapkan file Docker (Dockerfile, nginx.conf, docker-compose.yml)..."
cp "$TEMPLATE_DIR/Dockerfile" "$DOCKER_DIR/Dockerfile"

sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
    "$TEMPLATE_DIR/nginx.conf.tpl" > "$DOCKER_DIR/nginx.conf"

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

# --- Setup Laravel (dengan fallback composer update) ---
echo "-> Menjalankan composer install & migrate di dalam container..."
$DC -f "$COMPOSE_FILE" -p "$PROJECT_NAME" exec -T "app_${PROJECT_NAME}" bash -lc "
  # Coba composer install, jika gagal karena PHP version, jalankan composer update
  if composer install --no-interaction --prefer-dist --optimize-autoloader 2>&1 | tee /tmp/composer_output | grep -q 'does not satisfy'; then
    echo '⚠️  Dependencies tidak kompatibel dengan PHP $PHP_VERSION, menjalankan composer update...'
    composer update --no-interaction --prefer-dist --optimize-autoloader
  fi
  php artisan key:generate --force || true
  php artisan config:clear || true
  php artisan migrate --force || true
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
echo " PHP Versi   : $PHP_VERSION"
echo " Kredensial tersimpan di: $CREDS_FILE"
echo "=============================================="