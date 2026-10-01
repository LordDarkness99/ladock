#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Laravel Docker Auto-Deploy — Apache · Monolith + Microservices
#  v2.0
#
#  Mode MONOLITH (default — backward-compatible):
#    ./deploy.sh /path/to/laravel-project [http_port] [db_port] [php_version] [flags]
#    ./deploy.sh --cpmove=/path/cpmove-xxx.tar.gz [http_port] [db_port] [php_version] [flags]
#
#  Mode MICROSERVICES (otomatis jika terdeteksi >=2 sub-project Laravel):
#    ./deploy.sh /path/to/root-folder [gateway_port] [db_port] [flags]
#
#  Flags (opsional, bisa diletakkan di mana saja):
#    --cpmove=/path/cpmove.tar.gz  Extract project Laravel + dump DB dari backup cPanel
#    --cpmove-dest=/path/output    Folder tujuan extract cpmove (opsional)
#    --dump=/path/file.sql         Path eksplisit file dump DB (hanya mode monolith)
#    --force-import                Paksa import dump walau bukan deploy pertama
#    --skip-import                 Jangan pernah import dump
#    --mode=monolith|microservice  Paksa mode tertentu (override auto-detect)
#    --max-depth=N                 Kedalaman scan microservice (default: 5)
#    --base-app-port=N             Port awal untuk direct-access service (default: 8081)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"

# ── Parse flags & positional args ────────────────────────────────────────────
ARGS=()
DUMP_FILE=""
FORCE_IMPORT=0
SKIP_IMPORT=0
CPMOVE_FILE=""
CPMOVE_DEST=""
DEPLOY_MODE=""        # "" | "monolith" | "microservice"
MAX_DEPTH=5
BASE_APP_PORT=8081

for arg in "$@"; do
  case "$arg" in
    --dump=*)          DUMP_FILE="${arg#--dump=}" ;;
    --force-import)    FORCE_IMPORT=1 ;;
    --skip-import)     SKIP_IMPORT=1 ;;
    --cpmove=*)        CPMOVE_FILE="${arg#--cpmove=}" ;;
    --cpmove-dest=*)   CPMOVE_DEST="${arg#--cpmove-dest=}" ;;
    --mode=*)          DEPLOY_MODE="${arg#--mode=}" ;;
    --max-depth=*)     MAX_DEPTH="${arg#--max-depth=}" ;;
    --base-app-port=*) BASE_APP_PORT="${arg#--base-app-port=}" ;;
    *) ARGS+=("$arg") ;;
  esac
done

# Posisi argumen:
#   tanpa --cpmove : project_path [gateway/http_port] [db_port] [php_version]
#   dengan --cpmove: [gateway/http_port] [db_port] [php_version]
if [[ -n "$CPMOVE_FILE" ]]; then
  PROJECT_PATH=""
  HTTP_PORT="${ARGS[0]:-8080}"
  DB_PORT="${ARGS[1]:-3307}"
  PHP_VERSION_PARAM="${ARGS[2]:-}"
else
  PROJECT_PATH="${ARGS[0]:-}"
  HTTP_PORT="${ARGS[1]:-8080}"
  DB_PORT="${ARGS[2]:-3307}"
  PHP_VERSION_PARAM="${ARGS[3]:-}"
fi
GATEWAY_PORT="$HTTP_PORT"   # Dalam mode microservice, HTTP_PORT = Gateway port

# ── Utilitas ──────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
Usage (Monolith):
  $0 /path/to/laravel-project [http_port] [db_port] [php_version] [flags]
  $0 --cpmove=/path/cpmove-xxx.tar.gz [http_port] [db_port] [php_version] [flags]

Usage (Microservice — auto-detect atau paksa):
  $0 /path/to/root-folder [gateway_port] [db_port] [flags]
  $0 /path/to/root-folder --mode=microservice

Flags:
  --cpmove=FILE      Extract project + dump DB dari backup cPanel
  --cpmove-dest=DIR  Folder tujuan extract cpmove
  --dump=FILE        File dump .sql eksplisit (monolith saja)
  --force-import     Paksa import dump walau redeploy
  --skip-import      Jangan import dump sama sekali
  --mode=monolith|microservice   Override auto-detect
  --max-depth=N      Kedalaman scan microservice (default: 5)
  --base-app-port=N  Port awal direct-access per service (default: 8081)
EOF
}

log()  { echo "--> $*"; }
info() { echo "    $*"; }
hr()   { echo "=============================================="; }

# ── Cek dependensi ────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 tidak ditemukan. Install python3 terlebih dahulu."
  exit 1
fi

# ── Handle --cpmove ───────────────────────────────────────────────────────────
if [[ -n "$CPMOVE_FILE" ]]; then
  [[ ! -f "$CPMOVE_FILE" ]] && echo "File cpmove tidak ditemukan: $CPMOVE_FILE" && exit 1
  CPMOVE_FILE="$(cd "$(dirname "$CPMOVE_FILE")" && pwd)/$(basename "$CPMOVE_FILE")"

  if [[ -z "$CPMOVE_DEST" ]]; then
    CPMOVE_BASE="$(basename "$CPMOVE_FILE")"
    CPMOVE_BASE="${CPMOVE_BASE%.tar.gz}"; CPMOVE_BASE="${CPMOVE_BASE%.tgz}"
    CPMOVE_BASE="${CPMOVE_BASE#cpmove-}"
    CPMOVE_DEST="$(dirname "$CPMOVE_FILE")/${CPMOVE_BASE}_laravel"
  fi

  if [[ -d "$CPMOVE_DEST" && -n "$(ls -A "$CPMOVE_DEST" 2>/dev/null)" ]]; then
    log "Folder hasil extract cpmove sudah ada, pakai yang ada: $CPMOVE_DEST"
    PROJECT_PATH="$CPMOVE_DEST"
  else
    log "Mengekstrak project Laravel + dump DB dari arsip cpmove..."
    PROJECT_PATH="$(python3 "$SCRIPTS_DIR/extract_cpmove.py" "$CPMOVE_FILE" "$CPMOVE_DEST")"
  fi

  [[ -z "$PROJECT_PATH" || ! -d "$PROJECT_PATH" || ! -f "$PROJECT_PATH/artisan" ]] && \
    echo "Gagal mengekstrak/menemukan project Laravel dari arsip cpmove." && exit 1
  log "Project hasil extract cpmove: $PROJECT_PATH"
fi

# ── Auto-find project jika path kosong ───────────────────────────────────────
if [[ -z "$PROJECT_PATH" ]]; then
  log "Project path tidak diisi, mencari project Laravel di folder ini ($(pwd))..."
  mapfile -t FOUND < <(python3 "$SCRIPTS_DIR/find_laravel_projects.py" "$(pwd)")
  if [[ ${#FOUND[@]} -eq 0 ]]; then
    echo "Tidak ditemukan project Laravel di bawah $(pwd)."
    usage; exit 1
  elif [[ ${#FOUND[@]} -eq 1 ]]; then
    PROJECT_PATH="${FOUND[0]}"
    log "Ditemukan 1 project: $PROJECT_PATH"
  else
    echo "Ditemukan beberapa project Laravel, pilih salah satu:"
    select p in "${FOUND[@]}"; do
      [[ -n "$p" ]] && PROJECT_PATH="$p" && break
    done
  fi
fi

[[ -z "$PROJECT_PATH" ]] && usage && exit 1
[[ ! -d "$PROJECT_PATH" ]] && echo "Folder tidak ditemukan: $PROJECT_PATH" && exit 1
PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"

# ── Deteksi mode deployment ───────────────────────────────────────────────────
# Hitung jumlah sub-project Laravel di dalam PROJECT_PATH
MICROSERVICE_LIST_RAW=""
if [[ "$DEPLOY_MODE" != "monolith" ]]; then
  # Gunakan find_microservices.py untuk mendapatkan semua sub-project
  MICROSERVICE_LIST_RAW="$(python3 "$SCRIPTS_DIR/find_microservices.py" "$PROJECT_PATH" "$MAX_DEPTH" 2>/dev/null || true)"
  SVC_COUNT=$(echo "$MICROSERVICE_LIST_RAW" | grep -c $'\t' || true)

  if [[ -z "$DEPLOY_MODE" ]]; then
    if [[ "$SVC_COUNT" -ge 2 ]]; then
      DEPLOY_MODE="microservice"
    else
      DEPLOY_MODE="monolith"
    fi
  fi
fi

# ── Deteksi compose command ───────────────────────────────────────────────────
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "Docker Compose tidak ditemukan."
  exit 1
fi

# ============================================================================
# ██████████████████████  MODE MONOLITH  █████████████████████████████████████
# ============================================================================
if [[ "$DEPLOY_MODE" == "monolith" ]]; then

  # ── Validasi Laravel ────────────────────────────────────────────────────
  if [[ ! -f "$PROJECT_PATH/artisan" ]]; then
    echo "Folder '$PROJECT_PATH' bukan project Laravel yang valid (file 'artisan' tidak ditemukan)."
    exit 1
  fi

  RAW_NAME="$(basename "$PROJECT_PATH")"
  PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"

  # ── PHP & Composer version ───────────────────────────────────────────────
  if [[ -z "$PHP_VERSION_PARAM" ]]; then
    PHP_VERSION=$(python3 "$SCRIPTS_DIR/detect_php_version.py" "$PROJECT_PATH/composer.json")
    log "Deteksi otomatis PHP version: $PHP_VERSION"
  else
    PHP_VERSION="$PHP_VERSION_PARAM"
  fi

  if [[ "$(printf '%s\n' "$PHP_VERSION" "7.2" | sort -V | head -n1)" == "$PHP_VERSION" && "$PHP_VERSION" != "7.2" ]]; then
    COMPOSER_VERSION=1
  else
    COMPOSER_VERSION=2
  fi

  hr
  echo " Mode         : MONOLITH"
  echo " Project      : $PROJECT_NAME"
  echo " Path         : $PROJECT_PATH"
  echo " Web Server   : Apache"
  echo " HTTP Port    : $HTTP_PORT"
  echo " MySQL Port   : $DB_PORT"
  echo " PHP Version  : $PHP_VERSION"
  echo " Composer Ver : $COMPOSER_VERSION"
  hr

  DOCKER_DIR="$PROJECT_PATH/.docker"
  CREDS_FILE="$DOCKER_DIR/credentials.env"
  COMPOSE_DB_FILE="$PROJECT_PATH/.docker-compose-db.yml"
  COMPOSE_APP_FILE="$PROJECT_PATH/.docker-compose-app.yml"
  mkdir -p "$DOCKER_DIR"

  # ── Kredensial DB ────────────────────────────────────────────────────────
  FRESH_DEPLOY=0
  if [[ -f "$CREDS_FILE" ]]; then
    log "Menggunakan kredensial database yang sudah ada..."
    # shellcheck disable=SC1090
    source "$CREDS_FILE"
  else
    log "Membuat kredensial database baru..."
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

  # ── Render template ──────────────────────────────────────────────────────
  log "Menyiapkan file Docker (Dockerfile, apache-vhost.conf, .docker-compose-db.yml, .docker-compose-app.yml)..."
  rm -rf "$DOCKER_DIR/Dockerfile" "$DOCKER_DIR/apache-vhost.conf"
  cp "$TEMPLATE_DIR/Dockerfile" "$DOCKER_DIR/Dockerfile"

  sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
      "$TEMPLATE_DIR/apache-vhost.conf.tpl" > "$DOCKER_DIR/apache-vhost.conf"

  sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
      -e "s/__DB_PORT__/$DB_PORT/g" \
      -e "s/__DB_NAME__/$DB_NAME/g" \
      -e "s/__DB_USER__/$DB_USER/g" \
      -e "s/__DB_PASS__/$DB_PASS/g" \
      -e "s/__DB_ROOT_PASS__/$DB_ROOT_PASS/g" \
      "$TEMPLATE_DIR/docker-compose-db.yml.tpl" > "$COMPOSE_DB_FILE"

  sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
      -e "s/__HTTP_PORT__/$HTTP_PORT/g" \
      -e "s/__DB_NAME__/$DB_NAME/g" \
      -e "s/__DB_USER__/$DB_USER/g" \
      -e "s/__DB_PASS__/$DB_PASS/g" \
      -e "s/__PHP_VERSION__/$PHP_VERSION/g" \
      -e "s/__COMPOSER_VERSION__/$COMPOSER_VERSION/g" \
      "$TEMPLATE_DIR/docker-compose-app.yml.tpl" > "$COMPOSE_APP_FILE"

  # Hapus file compose lama jika ada
  rm -f "$PROJECT_PATH/.docker-compose.yml"

  # ── .env Laravel ────────────────────────────────────────────────────────
  cd "$PROJECT_PATH"
  if [[ ! -f .env ]]; then
    [[ -f .env.example ]] && cp .env.example .env && log ".env dibuat dari .env.example" || touch .env
  fi

  set_env() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env; then
      sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
    else
      echo "${key}=${val}" >> .env
    fi
  }

  set_env "DB_CONNECTION" "mysql"
  set_env "DB_HOST"       "db_${PROJECT_NAME}"
  set_env "DB_PORT"       "3306"
  set_env "DB_DATABASE"   "$DB_NAME"
  set_env "DB_USERNAME"   "$DB_USER"
  set_env "DB_PASSWORD"   "$DB_PASS"
  set_env "APP_URL"       "http://localhost:${HTTP_PORT}"

  for key in ASSET_URL ADMIN_HTTPS FORCE_HTTPS LARAVEL_ADMIN_HTTPS SESSION_SECURE_COOKIE; do
    grep -q "^${key}=" .env && case "$key" in
      ASSET_URL) set_env "$key" "http://localhost:${HTTP_PORT}" ;;
      *) set_env "$key" "false" ;;
    esac
  done

  # ── Down lama → Build → Up ───────────────────────────────────────────────
  log "Membersihkan container lama project ini (jika ada)..."
  $DC -f "$COMPOSE_APP_FILE" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
  $DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true

  log "Menjalankan container Database..."
  $DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" up -d

  # ── Tunggu MySQL ─────────────────────────────────────────────────────────
  log "Menunggu MySQL siap (hingga 90 detik)..."
  timeout=90; elapsed=0
  until $DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" exec -T "db_${PROJECT_NAME}" \
        mysql -uroot -p"$DB_ROOT_PASS" -e "SELECT 1" >/dev/null 2>&1; do
    [[ $elapsed -ge $timeout ]] && echo "MySQL tidak siap setelah $timeout detik." && exit 1
    sleep 2; elapsed=$((elapsed+2)); info "... menunggu ($elapsed/${timeout}s)"
  done
  echo "MySQL siap!"

  log "Build image & menjalankan container App..."
  $DC -f "$COMPOSE_APP_FILE" -p "$PROJECT_NAME" up -d --build

  # ── Import dump ──────────────────────────────────────────────────────────
  SHOULD_IMPORT=0
  [[ $SKIP_IMPORT -eq 0 ]] && { [[ $FRESH_DEPLOY -eq 1 || $FORCE_IMPORT -eq 1 || -n "$DUMP_FILE" ]] && SHOULD_IMPORT=1; }

  if [[ $SHOULD_IMPORT -eq 1 ]]; then
    log "Mencari & mengimpor dump database (.sql) jika ada..."
    DUMP_ARGS=(
      --project-path "$PROJECT_PATH"
      --project-name "$PROJECT_NAME"
      --compose-file "$COMPOSE_DB_FILE"
      --db-name      "$DB_NAME"
      --db-root-pass "$DB_ROOT_PASS"
      --dc           "$DC"
    )
    [[ -n "$DUMP_FILE" ]] && DUMP_ARGS+=(--dump "$DUMP_FILE")
    python3 "$SCRIPTS_DIR/db_import.py" "${DUMP_ARGS[@]}"
  else
    log "Lewati import dump (bukan deploy pertama; pakai --force-import untuk paksa)."
  fi

  # ── Setup Laravel ─────────────────────────────────────────────────────────
  log "Menjalankan composer install & migrate di dalam container..."
  $DC -f "$COMPOSE_APP_FILE" -p "$PROJECT_NAME" exec -T "app_${PROJECT_NAME}" bash -lc "
    set -e
    if composer install --no-interaction --prefer-dist --optimize-autoloader 2>&1 | tee /tmp/composer_output | grep -q 'does not satisfy'; then
      echo '⚠️  Dependencies tidak kompatibel, menjalankan composer update...'
      composer update --no-interaction --prefer-dist --optimize-autoloader
    fi
    rm -f bootstrap/cache/*.php 2>/dev/null || true
    rm -f storage/framework/sessions/* 2>/dev/null || true
    rm -f storage/framework/views/*.php 2>/dev/null || true
    php artisan config:clear || true
    php artisan route:clear  || true
    php artisan view:clear   || true
    php artisan cache:clear  || true
    php artisan key:generate --force || true
    rm -f bootstrap/cache/*.php 2>/dev/null || true
    php artisan config:clear || true
    php artisan route:clear  || true
    php artisan migrate --force || true
    php artisan storage:link  || true
  "

  echo ""
  hr
  echo " SELESAI — Laravel project '$PROJECT_NAME' sudah live"
  echo " Akses Web   : http://localhost:$HTTP_PORT"
  echo " MySQL       : localhost:$DB_PORT"
  echo "   DB Name   : $DB_NAME"
  echo "   DB User   : $DB_USER"
  echo "   DB Pass   : $DB_PASS"
  echo " PHP Versi   : $PHP_VERSION"
  echo " Kredensial  : $CREDS_FILE"
  hr
  exit 0
fi

# ============================================================================
# ████████████████████  MODE MICROSERVICE  ███████████████████████████████████
# ============================================================================

log "Mode MICROSERVICE diaktifkan"

# ── Parse daftar service dari scanner ────────────────────────────────────────
# Format tiap baris: <service_name>\t<path>
declare -a SVC_NAMES=()
declare -A SVC_PATHS=()

while IFS=$'\t' read -r svc_name svc_path; do
  [[ -z "$svc_name" || -z "$svc_path" ]] && continue
  SVC_NAMES+=("$svc_name")
  SVC_PATHS["$svc_name"]="$svc_path"
done <<< "$MICROSERVICE_LIST_RAW"

if [[ ${#SVC_NAMES[@]} -eq 0 ]]; then
  echo "Tidak ada sub-project Laravel ditemukan di: $PROJECT_PATH"
  echo "Jalankan dengan --mode=monolith jika ini adalah project monolith."
  exit 1
fi

# ── Nama project dari folder root ────────────────────────────────────────────
RAW_NAME="$(basename "$PROJECT_PATH")"
PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"

# ── Assign port ke masing-masing service ─────────────────────────────────────
# Gateway: GATEWAY_PORT (= HTTP_PORT / ARGS[1])
# Service direct: BASE_APP_PORT, BASE_APP_PORT+1, ...
declare -A SVC_HTTP_PORTS=()
declare -A SVC_PHP_VERSIONS=()
declare -A SVC_COMPOSER_VERSIONS=()
declare -A SVC_DB_NAMES=()
declare -A SVC_DB_USERS=()
declare -A SVC_DB_PASSES=()

CURRENT_APP_PORT=$BASE_APP_PORT
for svc_name in "${SVC_NAMES[@]}"; do
  SVC_HTTP_PORTS["$svc_name"]=$CURRENT_APP_PORT
  CURRENT_APP_PORT=$((CURRENT_APP_PORT + 1))

  # Deteksi PHP versi per service
  svc_path="${SVC_PATHS[$svc_name]}"
  php_ver=$(python3 "$SCRIPTS_DIR/detect_php_version.py" "$svc_path/composer.json" 2>/dev/null || echo "8.4")
  SVC_PHP_VERSIONS["$svc_name"]="$php_ver"

  if [[ "$(printf '%s\n' "$php_ver" "7.2" | sort -V | head -n1)" == "$php_ver" && "$php_ver" != "7.2" ]]; then
    SVC_COMPOSER_VERSIONS["$svc_name"]=1
  else
    SVC_COMPOSER_VERSIONS["$svc_name"]=2
  fi
done

hr
echo " Mode         : MICROSERVICE"
echo " Project Root : $PROJECT_PATH"
echo " Project Name : $PROJECT_NAME"
echo " Gateway Port : $GATEWAY_PORT"
echo " MySQL Port   : $DB_PORT"
echo " Services     : ${#SVC_NAMES[@]}"
for svc_name in "${SVC_NAMES[@]}"; do
  echo "   [$svc_name] PHP ${SVC_PHP_VERSIONS[$svc_name]} | direct :${SVC_HTTP_PORTS[$svc_name]} | route /${svc_name}/"
done
hr

# ── .docker folder di root project ───────────────────────────────────────────
DOCKER_DIR="$PROJECT_PATH/.docker"
CREDS_DIR="$DOCKER_DIR/credentials"
COMPOSE_FILE="$PROJECT_PATH/.docker-compose.yml"
GATEWAY_DIR="$DOCKER_DIR/gateway"
mkdir -p "$DOCKER_DIR" "$CREDS_DIR" "$GATEWAY_DIR"

# ── DB Root password (shared, idempotent) ────────────────────────────────────
ROOT_PASS_FILE="$CREDS_DIR/.db_root_pass"
if [[ -f "$ROOT_PASS_FILE" ]]; then
  DB_ROOT_PASS="$(cat "$ROOT_PASS_FILE")"
else
  DB_ROOT_PASS="$(openssl rand -hex 16)"
  echo "$DB_ROOT_PASS" > "$ROOT_PASS_FILE"
  chmod 600 "$ROOT_PASS_FILE"
fi

# ── Kredensial per service (idempotent) ──────────────────────────────────────
FRESH_DEPLOYS=()
for svc_name in "${SVC_NAMES[@]}"; do
  CREDS_FILE="$CREDS_DIR/${svc_name}.env"
  if [[ -f "$CREDS_FILE" ]]; then
    log "[$svc_name] Menggunakan kredensial DB yang sudah ada..."
    # shellcheck disable=SC1090
    source "$CREDS_FILE"
    SVC_DB_NAMES["$svc_name"]="$DB_NAME"
    SVC_DB_USERS["$svc_name"]="$DB_USER"
    SVC_DB_PASSES["$svc_name"]="$DB_PASS"
  else
    log "[$svc_name] Membuat kredensial DB baru..."
    FRESH_DEPLOYS+=("$svc_name")
    # Nama pendek service untuk username (max 32 char MySQL)
    SHORT_SVC="$(echo "${PROJECT_NAME}_${svc_name}" | cut -c1-20)"
    DB_NAME="${PROJECT_NAME}_${svc_name}_db"
    DB_USER="${SHORT_SVC}_u"
    DB_PASS="$(openssl rand -hex 12)"
    SVC_DB_NAMES["$svc_name"]="$DB_NAME"
    SVC_DB_USERS["$svc_name"]="$DB_USER"
    SVC_DB_PASSES["$svc_name"]="$DB_PASS"
    cat > "$CREDS_FILE" <<EOF
DB_NAME=$DB_NAME
DB_USER=$DB_USER
DB_PASS=$DB_PASS
DB_ROOT_PASS=$DB_ROOT_PASS
EOF
    chmod 600 "$CREDS_FILE"
  fi
done

# ── Bangun argumen untuk generator ───────────────────────────────────────────
# Format: name1:port1,name2:port2,...
SERVICES_ARG=""
PHP_VERS_ARG=""
COMP_VERS_ARG=""
DB_CREDS_ARG=""
SVC_PATHS_ARG=""
for svc_name in "${SVC_NAMES[@]}"; do
  [[ -n "$SERVICES_ARG" ]] && SERVICES_ARG+=","
  SERVICES_ARG+="${svc_name}:${SVC_HTTP_PORTS[$svc_name]}"

  [[ -n "$PHP_VERS_ARG" ]] && PHP_VERS_ARG+=","
  PHP_VERS_ARG+="${svc_name}:${SVC_PHP_VERSIONS[$svc_name]}"

  [[ -n "$COMP_VERS_ARG" ]] && COMP_VERS_ARG+=","
  COMP_VERS_ARG+="${svc_name}:${SVC_COMPOSER_VERSIONS[$svc_name]}"

  [[ -n "$DB_CREDS_ARG" ]] && DB_CREDS_ARG+="|"
  DB_CREDS_ARG+="${svc_name}:${SVC_DB_NAMES[$svc_name]}:${SVC_DB_USERS[$svc_name]}:${SVC_DB_PASSES[$svc_name]}"

  # Bangun peta service-paths: name1:/path1,name2:/path2,...
  [[ -n "${SVC_PATHS_ARG:-}" ]] && SVC_PATHS_ARG+=","
  SVC_PATHS_ARG+="${svc_name}:${SVC_PATHS[$svc_name]}"
done

COMPOSE_DB_FILE="$PROJECT_PATH/.docker-compose-db.yml"
COMPOSE_APP_FILE="$PROJECT_PATH/.docker-compose-app.yml"

# ── Generate docker-compose-db.yml & docker-compose-app.yml ──────────────────
log "Men-generate docker-compose-db.yml dan docker-compose-app.yml (${#SVC_NAMES[@]} services + gateway + DBs)..."

python3 "$SCRIPTS_DIR/generate_compose.py" \
  --project           "$PROJECT_NAME" \
  --services          "$SERVICES_ARG" \
  --service-paths     "${SVC_PATHS_ARG:-}" \
  --docker-dir        "$DOCKER_DIR" \
  --gateway-port      "$GATEWAY_PORT" \
  --db-port           "$DB_PORT" \
  --db-root-pass      "$DB_ROOT_PASS" \
  --php-versions      "$PHP_VERS_ARG" \
  --composer-versions "$COMP_VERS_ARG" \
  --db-creds          "$DB_CREDS_ARG" \
  --output-dir        "$PROJECT_PATH"

rm -f "$PROJECT_PATH/.docker-compose.yml"

# ── Salin Dockerfile app ke folder .docker ───────────────────────────────────
rm -rf "$DOCKER_DIR/Dockerfile" "$DOCKER_DIR/apache-vhost.conf" "$DOCKER_DIR/apache-gateway.conf"
cp "$TEMPLATE_DIR/Dockerfile" "$DOCKER_DIR/Dockerfile"
sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
    "$TEMPLATE_DIR/apache-vhost.conf.tpl" > "$DOCKER_DIR/apache-vhost.conf"

# ── Siapkan Gateway ──────────────────────────────────────────────────────────
log "Men-generate konfigurasi Apache Gateway..."
GATEWAY_CONF_RAW="$(python3 "$SCRIPTS_DIR/generate_gateway_conf.py" \
  --project "$PROJECT_NAME" \
  --services "$SERVICES_ARG" \
  --gateway-port "$GATEWAY_PORT")"

# Pisahkan: bagian sebelum marker = conf, bagian setelah = dashboard html
GATEWAY_CONF="${GATEWAY_CONF_RAW%%# __DASHBOARD_HTML_MARKER__*}"
DASHBOARD_HTML="${GATEWAY_CONF_RAW##*# __DASHBOARD_HTML_MARKER__}"

echo "$GATEWAY_CONF" > "$DOCKER_DIR/apache-gateway.conf"
echo "$DASHBOARD_HTML" > "$GATEWAY_DIR/dashboard.html"

# Dockerfile & httpd.conf gateway
cp "$TEMPLATE_DIR/gateway.Dockerfile" "$GATEWAY_DIR/Dockerfile"
cp "$TEMPLATE_DIR/gateway-httpd.conf" "$GATEWAY_DIR/httpd.conf"

# ── .env setiap service ───────────────────────────────────────────────────────
log "Mengkonfigurasi .env setiap service..."
for svc_name in "${SVC_NAMES[@]}"; do
  svc_path="${SVC_PATHS[$svc_name]}"
  db_name="${SVC_DB_NAMES[$svc_name]}"
  db_user="${SVC_DB_USERS[$svc_name]}"
  db_pass="${SVC_DB_PASSES[$svc_name]}"
  svc_port="${SVC_HTTP_PORTS[$svc_name]}"

  cd "$svc_path"
  if [[ ! -f .env ]]; then
    [[ -f .env.example ]] && cp .env.example .env || touch .env
  fi

  set_env() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env; then
      sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
    else
      echo "${key}=${val}" >> .env
    fi
  }

  set_env "DB_CONNECTION" "mysql"
  set_env "DB_HOST"       "db_${svc_name}"
  set_env "DB_PORT"       "3306"
  set_env "DB_DATABASE"   "$db_name"
  set_env "DB_USERNAME"   "$db_user"
  set_env "DB_PASSWORD"   "$db_pass"
  # URL melalui gateway (canonical), direct port untuk dev
  set_env "APP_URL" "http://localhost:${GATEWAY_PORT}/${svc_name}"

  for key in ASSET_URL ADMIN_HTTPS FORCE_HTTPS LARAVEL_ADMIN_HTTPS SESSION_SECURE_COOKIE; do
    grep -q "^${key}=" .env && case "$key" in
      ASSET_URL) set_env "$key" "http://localhost:${GATEWAY_PORT}/${svc_name}" ;;
      *) set_env "$key" "false" ;;
    esac
  done

  # Injeksi URL service lain ke .env (inter-service discovery)
  for other_svc in "${SVC_NAMES[@]}"; do
    [[ "$other_svc" == "$svc_name" ]] && continue
    KEY="SERVICE_$(echo "$other_svc" | tr '[:lower:]' '[:upper:]')_URL"
    set_env "$KEY" "http://app_${other_svc}:80"
  done

  log "[$svc_name] .env siap"
done

# ── Down container lama ───────────────────────────────────────────────────────
log "Membersihkan container lama (jika ada)..."
cd "$PROJECT_PATH"
$DC -f "$COMPOSE_APP_FILE" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
$DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true

# ── Build & Up ────────────────────────────────────────────────────────────────
log "Menjalankan container Database..."
$DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" up -d

# ── Tunggu MySQL tiap service ──────────────────────────────────────────────────
log "Menunggu MySQL tiap service siap (hingga 90 detik)..."
for svc_name in "${SVC_NAMES[@]}"; do
  timeout=90; elapsed=0
  until $DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" exec -T "db_${svc_name}" \
        mysql -uroot -p"$DB_ROOT_PASS" -e "SELECT 1" >/dev/null 2>&1; do
    [[ $elapsed -ge $timeout ]] && echo "MySQL db_${svc_name} tidak siap setelah $timeout detik." && exit 1
    sleep 2; elapsed=$((elapsed+2)); info "... menunggu db_${svc_name} ($elapsed/${timeout}s)"
  done
  log "MySQL db_${svc_name} siap!"
done

# ── Buat database & user per service ─────────────────────────────────────────
log "Memastikan database & user MySQL per service..."
for svc_name in "${SVC_NAMES[@]}"; do
  db_name="${SVC_DB_NAMES[$svc_name]}"
  db_user="${SVC_DB_USERS[$svc_name]}"
  db_pass="${SVC_DB_PASSES[$svc_name]}"

  $DC -f "$COMPOSE_DB_FILE" -p "$PROJECT_NAME" exec -T "db_${svc_name}" \
    mysql -uroot -p"$DB_ROOT_PASS" -e "
      CREATE DATABASE IF NOT EXISTS \`${db_name}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
      CREATE USER IF NOT EXISTS '${db_user}'@'%' IDENTIFIED BY '${db_pass}';
      GRANT ALL PRIVILEGES ON \`${db_name}\`.* TO '${db_user}'@'%';
      FLUSH PRIVILEGES;
    " >/dev/null 2>&1
  log "[$svc_name] DB '${db_name}' & user '${db_user}' di container db_${svc_name} siap"
done

log "Build image & menjalankan semua container App & Gateway..."
$DC -f "$COMPOSE_APP_FILE" -p "$PROJECT_NAME" up -d --build

# ── Import dump & setup Laravel per service ───────────────────────────────────
for svc_name in "${SVC_NAMES[@]}"; do
  svc_path="${SVC_PATHS[$svc_name]}"
  db_name="${SVC_DB_NAMES[$svc_name]}"
  db_user="${SVC_DB_USERS[$svc_name]}"
  php_ver="${SVC_PHP_VERSIONS[$svc_name]}"

  # Apakah ini fresh deploy?
  IS_FRESH=0
  for fd in "${FRESH_DEPLOYS[@]:-}"; do
    [[ "$fd" == "$svc_name" ]] && IS_FRESH=1 && break
  done

  SHOULD_IMPORT=0
  [[ $SKIP_IMPORT -eq 0 ]] && { [[ $IS_FRESH -eq 1 || $FORCE_IMPORT -eq 1 ]] && SHOULD_IMPORT=1; }

  if [[ $SHOULD_IMPORT -eq 1 ]]; then
    log "[$svc_name] Mencari & mengimpor dump database..."
    python3 "$SCRIPTS_DIR/db_import.py" \
      --project-path "$svc_path" \
      --project-name "$PROJECT_NAME" \
      --compose-file "$COMPOSE_DB_FILE" \
      --db-name      "$db_name" \
      --db-root-pass "$DB_ROOT_PASS" \
      --dc           "$DC"
  else
    log "[$svc_name] Lewati import dump."
  fi

  # Setup Laravel
  log "[$svc_name] Menjalankan composer install & migrate..."
  $DC -f "$COMPOSE_APP_FILE" -p "$PROJECT_NAME" exec -T "app_${svc_name}" bash -lc "
    set -e
    cd /var/www
    if composer install --no-interaction --prefer-dist --optimize-autoloader 2>&1 | tee /tmp/composer_out | grep -q 'does not satisfy'; then
      echo '⚠️  Composer install gagal, coba update...'
      composer update --no-interaction --prefer-dist --optimize-autoloader
    fi
    rm -f bootstrap/cache/*.php storage/framework/sessions/* storage/framework/views/*.php 2>/dev/null || true
    php artisan config:clear || true
    php artisan route:clear  || true
    php artisan view:clear   || true
    php artisan cache:clear  || true
    php artisan key:generate --force || true
    rm -f bootstrap/cache/*.php 2>/dev/null || true
    php artisan config:clear || true
    php artisan route:clear  || true
    php artisan migrate --force || true
    php artisan storage:link  || true
  "
  log "[$svc_name] ✓ Selesai"
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
hr
echo " SELESAI — Microservice '$PROJECT_NAME' sudah live!"
echo ""
echo " Gateway (pintu utama)  : http://localhost:${GATEWAY_PORT}/"
echo " MySQL                  : localhost:${DB_PORT}"
echo ""
echo " Service Routes:"
for svc_name in "${SVC_NAMES[@]}"; do
  echo "   /${svc_name}/  ->  http://localhost:${GATEWAY_PORT}/${svc_name}/"
  echo "            direct  ->  http://localhost:${SVC_HTTP_PORTS[$svc_name]}"
  echo "            DB      ->  ${SVC_DB_NAMES[$svc_name]} (user: ${SVC_DB_USERS[$svc_name]})"
done
echo ""
echo " Kredensial : $CREDS_DIR/"
hr