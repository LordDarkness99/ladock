#!/usr/bin/env bash
# ==============================================================================
#  LaDock — Universal Web App & Laravel Docker Auto-Deploy
#  v3.0 — Modular Architecture with Full Stack Detection & Clean Project Layout
#
#  Mode MONOLITH & MICROSERVICES
#  Mendukung:
#    - Ekstraksi otomatis arsip .zip, .tar.gz, .tgz dengan proteksi Zip-Slip & corrupt
#    - Deteksi stack luas (PHP, Node.js, Python, Go, dll.) -> stack.json
#    - Restrukturisasi folder: <app>/src/, docker-compose.yml, Dockerfile, stack.json, logs/
#    - Aplikasi di docker/apps/<app>/ dan database di docker/db/
# ==============================================================================

set -euo pipefail
trap 'echo "❌ [DEPLOY ERROR] Terjadi kegagalan pada baris $LINENO!" >&2' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DIR="$SCRIPT_DIR/templates"
SCRIPTS_DIR="$SCRIPT_DIR/scripts"
CONFIG_FILE="$SCRIPT_DIR/config.json"
CENTRAL_ENV_FILE="$SCRIPT_DIR/.ladock_db.env"

# ── Baca konfigurasi default dari config.json jika ada ────────────────────────
DEFAULT_DEPLOY_ROOT="$SCRIPT_DIR/docker/apps"
DEFAULT_MONOLITH_PORT=8080
DEFAULT_BASE_APP_PORT=8081
DEFAULT_DB_PORT=3308
DEFAULT_MEMORY_LIMIT=512M

if [[ -f "$CONFIG_FILE" ]] && command -v python3 >/dev/null 2>&1; then
  DEFAULT_DEPLOY_ROOT="$(python3 -c "import json, os; d=json.load(open('$CONFIG_FILE')); r=d.get('deploy_root', '$DEFAULT_DEPLOY_ROOT'); print(os.path.abspath(os.path.join('$SCRIPT_DIR', r)) if not os.path.isabs(r) else r)" 2>/dev/null || echo "$DEFAULT_DEPLOY_ROOT")"
  DEFAULT_MONOLITH_PORT="$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('default_ports', {}).get('monolith_http', $DEFAULT_MONOLITH_PORT))" 2>/dev/null || echo "$DEFAULT_MONOLITH_PORT")"
  DEFAULT_BASE_APP_PORT="$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('default_ports', {}).get('base_app_port', $DEFAULT_BASE_APP_PORT))" 2>/dev/null || echo "$DEFAULT_BASE_APP_PORT")"
  DEFAULT_MEMORY_LIMIT="$(python3 -c "import json; d=json.load(open('$CONFIG_FILE')); print(d.get('resources', {}).get('memory_limit', '$DEFAULT_MEMORY_LIMIT'))" 2>/dev/null || echo "$DEFAULT_MEMORY_LIMIT")"
fi

# ── Parse flags & positional args ────────────────────────────────────────────
ARGS=()
DUMP_FILE=""
FORCE_IMPORT=0
SKIP_IMPORT=0
ARCHIVE_FILE=""
ARCHIVE_DEST=""
DEPLOY_MODE=""        # "" | "monolith" | "microservice"
MAX_DEPTH=5
BASE_APP_PORT="$DEFAULT_BASE_APP_PORT"
MEMORY_LIMIT="$DEFAULT_MEMORY_LIMIT"

for arg in "$@"; do
  case "$arg" in
    --dump=*)          DUMP_FILE="${arg#--dump=}" ;;
    --force-import)    FORCE_IMPORT=1 ;;
    --skip-import)     SKIP_IMPORT=1 ;;
    --archive=*)       ARCHIVE_FILE="${arg#--archive=}" ;;
    --zip=*)           ARCHIVE_FILE="${arg#--zip=}" ;;
    --cpmove=*)        ARCHIVE_FILE="${arg#--cpmove=}" ;;
    --cpmove-dest=*)   ARCHIVE_DEST="${arg#--cpmove-dest=}" ;;
    --dest=*)          ARCHIVE_DEST="${arg#--dest=}" ;;
    --mode=*)          DEPLOY_MODE="${arg#--mode=}" ;;
    --max-depth=*)     MAX_DEPTH="${arg#--max-depth=}" ;;
    --base-app-port=*) BASE_APP_PORT="${arg#--base-app-port=}" ;;
    --memory-limit=*)  MEMORY_LIMIT="${arg#--memory-limit=}" ;;
    *) ARGS+=("$arg") ;;
  esac
done

if [[ ! "$MEMORY_LIMIT" =~ ^[1-9][0-9]*([.][0-9]+)?([bBkKmMgG]|[kKmMgG][bB])?$ ]]; then
  echo "❌ Batas memori tidak valid: '$MEMORY_LIMIT'. Gunakan ukuran seperti 512M atau 1G." >&2
  exit 1
fi

# Deteksi otomatis jika argumen pertama adalah file arsip (.zip, .tar.gz, dll.)
FIRST_ARG="${ARGS[0]:-}"
if [[ -z "$ARCHIVE_FILE" && -n "$FIRST_ARG" && -f "$FIRST_ARG" ]]; then
  LOWER_FIRST="$(echo "$FIRST_ARG" | tr '[:upper:]' '[:lower:]')"
  if [[ "$LOWER_FIRST" =~ \.(zip|tar\.gz|tgz|tar\.bz2|tar)$ ]]; then
    ARCHIVE_FILE="$FIRST_ARG"
    # Geser argumen
    ARGS=("${ARGS[@]:1}")
  fi
fi

if [[ -n "$ARCHIVE_FILE" ]]; then
  PROJECT_PATH=""
  HTTP_PORT="${ARGS[0]:-$DEFAULT_MONOLITH_PORT}"
  DB_PORT="${ARGS[1]:-$DEFAULT_DB_PORT}"
  PHP_VERSION_PARAM="${ARGS[2]:-}"
else
  PROJECT_PATH="${ARGS[0]:-}"
  HTTP_PORT="${ARGS[1]:-$DEFAULT_MONOLITH_PORT}"
  DB_PORT="${ARGS[2]:-$DEFAULT_DB_PORT}"
  PHP_VERSION_PARAM="${ARGS[3]:-}"
fi
GATEWAY_PORT="$HTTP_PORT"

# ── Utilitas ──────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
LaDock Universal Auto-Deploy v3.0

Penggunaan (Monolith / Standalone App):
  $0 /path/to/project [http_port] [db_port] [php_version] [flags]
  $0 /path/to/archive.zip [http_port] [db_port] [php_version] [flags]
  $0 --archive=/path/archive.zip [http_port] [db_port] [php_version] [flags]
  $0 --cpmove=/path/cpmove-xxx.tar.gz [http_port] [db_port] [php_version] [flags]

Penggunaan (Microservices):
  $0 /path/to/root-folder [gateway_port] [db_port] [flags]
  $0 /path/to/root-folder --mode=microservice

Flags:
  --archive=FILE     Extract project dari .zip, .tar.gz, atau .tgz
  --cpmove=FILE      Alias untuk arsip backup cPanel
  --dest=DIR         Folder tujuan extract arsip
  --dump=FILE        File dump .sql eksplisit
  --force-import     Paksa import dump database
  --skip-import      Lewati proses import dump
  --mode=MODE        Paksa mode: 'monolith' atau 'microservice'
  --max-depth=N      Kedalaman scan microservice (default: 5)
  --base-app-port=N  Port awal direct-access per service (default: 8081)
  --memory-limit=SIZE Batas memori untuk setiap service (default: $DEFAULT_MEMORY_LIMIT; contoh: 1G)
EOF
}

log()  { echo -e "--> $*"; }
info() { echo -e "    $*"; }
hr()   { echo "============================================================"; }

# ── Cek Dependensi Sistem ─────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ python3 tidak ditemukan. Mohon install python3."
  exit 1
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  echo "❌ Docker Compose tidak ditemukan."
  exit 1
fi

# ── Ekstraksi Arsip (.zip / .tar.gz / .tgz) ───────────────────────────────────
if [[ -n "$ARCHIVE_FILE" ]]; then
  [[ ! -f "$ARCHIVE_FILE" ]] && echo "❌ File arsip tidak ditemukan: $ARCHIVE_FILE" && exit 1
  ARCHIVE_FILE="$(cd "$(dirname "$ARCHIVE_FILE")" && pwd)/$(basename "$ARCHIVE_FILE")"

  if [[ -z "$ARCHIVE_DEST" ]]; then
    ARCHIVE_BASE="$(basename "$ARCHIVE_FILE")"
    for ext in ".tar.gz" ".tgz" ".zip" ".tar.bz2" ".tar"; do
      if [[ "$ARCHIVE_BASE" == *"$ext" ]]; then
        ARCHIVE_BASE="${ARCHIVE_BASE%"$ext"}"
        break
      fi
    done
    ARCHIVE_BASE="${ARCHIVE_BASE#cpmove-}"
    # Gunakan DEFAULT_DEPLOY_ROOT jika ada
    if [[ -d "$DEFAULT_DEPLOY_ROOT" || "$DEFAULT_DEPLOY_ROOT" == /* ]]; then
      mkdir -p "$DEFAULT_DEPLOY_ROOT"
      ARCHIVE_DEST="$DEFAULT_DEPLOY_ROOT/${ARCHIVE_BASE}"
    else
      ARCHIVE_DEST="$(dirname "$ARCHIVE_FILE")/${ARCHIVE_BASE}"
    fi
  fi

  RAW_EXTRACT_APP="$(basename "$ARCHIVE_DEST")"
  CLEAN_EXTRACT_APP="$(echo "$RAW_EXTRACT_APP" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
  CENTRAL_DB_DIR="$SCRIPT_DIR/mysql/db/$CLEAN_EXTRACT_APP"
  mkdir -p "$CENTRAL_DB_DIR"

  log "Mengekstrak dan memvalidasi arsip ($ARCHIVE_FILE)..."
  PROJECT_PATH="$(python3 "$SCRIPTS_DIR/extract_archive.py" "$ARCHIVE_FILE" "$ARCHIVE_DEST" "$CENTRAL_DB_DIR")"

  [[ -z "$PROJECT_PATH" || ! -d "$PROJECT_PATH" ]] && echo "❌ Gagal mengekstrak arsip." && exit 1
  log "Folder project hasil ekstraksi: $PROJECT_PATH"
fi

# ── Auto-find project jika path kosong ─────────────────────────────────────────
if [[ -z "$PROJECT_PATH" ]]; then
  log "Project path tidak diisi, memindai direktori saat ini ($(pwd))..."
  mapfile -t FOUND < <(python3 "$SCRIPTS_DIR/find_laravel_projects.py" "$(pwd)")
  if [[ ${#FOUND[@]} -eq 0 ]]; then
    echo "Tidak ditemukan project di bawah $(pwd)."
    usage; exit 1
  elif [[ ${#FOUND[@]} -eq 1 ]]; then
    PROJECT_PATH="${FOUND[0]}"
    log "Ditemukan 1 project: $PROJECT_PATH"
  else
    echo "Ditemukan beberapa project, pilih salah satu:"
    select p in "${FOUND[@]}"; do
      [[ -n "$p" ]] && PROJECT_PATH="$p" && break
    done
  fi
fi

[[ -z "$PROJECT_PATH" ]] && usage && exit 1
[[ ! -d "$PROJECT_PATH" ]] && echo "❌ Direktori tidak ditemukan: $PROJECT_PATH" && exit 1
PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"

# ── Deteksi Mode Deployment (Monolith vs Microservices) ───────────────────────
MICROSERVICE_LIST_RAW=""
if [[ "$DEPLOY_MODE" != "monolith" ]]; then
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

# ==============================================================================
# ██████████████████████  MODE MONOLITH  █████████████████████████████████████
# ==============================================================================
if [[ "$DEPLOY_MODE" == "monolith" ]]; then

  RAW_NAME="$(basename "$PROJECT_PATH")"
  PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"

  # ── Pusatkan semua aplikasi ke folder docker/apps/<app_name>/ ──────────────
  TARGET_DEPLOY_DIR="$DEFAULT_DEPLOY_ROOT/$PROJECT_NAME"
  LEGACY_DEPLOY_DIR="$SCRIPT_DIR/docker/$PROJECT_NAME"
  if [[ ! -e "$TARGET_DEPLOY_DIR" && -d "$LEGACY_DEPLOY_DIR" ]]; then
    log "Memindahkan deployment lama ke struktur docker/apps/..."
    mkdir -p "$(dirname "$TARGET_DEPLOY_DIR")"
    mv "$LEGACY_DEPLOY_DIR" "$TARGET_DEPLOY_DIR"
    if [[ "$PROJECT_PATH" == "$LEGACY_DEPLOY_DIR" || "$PROJECT_PATH" == "$LEGACY_DEPLOY_DIR/src" ]]; then
      PROJECT_PATH="$TARGET_DEPLOY_DIR${PROJECT_PATH#"$LEGACY_DEPLOY_DIR"}"
    fi
  fi
  if [[ "$PROJECT_PATH" != "$TARGET_DEPLOY_DIR" && "$PROJECT_PATH" != "$TARGET_DEPLOY_DIR/src" ]]; then
    log "Menata & menyalin project ke direktori terpusat: $TARGET_DEPLOY_DIR ..."
    mkdir -p "$TARGET_DEPLOY_DIR/src"
    if [[ -d "$PROJECT_PATH/src" ]]; then
      cp -a "$PROJECT_PATH/src/." "$TARGET_DEPLOY_DIR/src/"
    else
      # Salin berkas project selain .git, logs, docker-compose ke src/
      for f in "$PROJECT_PATH"/* "$PROJECT_PATH"/.[!.]* "$PROJECT_PATH"/..?*; do
        [[ ! -e "$f" ]] && continue
        b="$(basename "$f")"
        if [[ "$b" != ".git" && "$b" != "logs" && "$b" != "docker-compose.yml" && "$b" != "Dockerfile" ]]; then
          cp -a "$f" "$TARGET_DEPLOY_DIR/src/" 2>/dev/null || true
        fi
      done
    fi
    PROJECT_PATH="$TARGET_DEPLOY_DIR"
  fi

  # ── Restrukturisasi Folder Deployment: docker/apps/<app_name>/ ─────────────
  SRC_DIR="$PROJECT_PATH/src"
  if [[ ! -d "$SRC_DIR" ]]; then
    log "Menata struktur folder ke layout standar (memindahkan source code ke 'src/')..."
    mkdir -p "$SRC_DIR"
    for item in "$PROJECT_PATH"/* "$PROJECT_PATH"/.[!.]* "$PROJECT_PATH"/..?*; do
      [[ ! -e "$item" ]] && continue
      base="$(basename "$item")"
      if [[ "$base" != "src" && "$base" != ".git" && "$base" != "mysql" && "$base" != "logs" && \
            "$base" != "docker-compose.yml" && "$base" != "Dockerfile" && "$base" != "apache-vhost.conf" && \
            "$base" != "stack.json" && "$base" != ".dockerignore" && "$base" != ".credentials.env" ]]; then
        mv "$item" "$SRC_DIR/" 2>/dev/null || true
      fi
    done
  fi

  # Hapus file legacy / hidden Docker lama jika ada
  rm -rf "$PROJECT_PATH/.docker" "$PROJECT_PATH/.docker-compose-app.yml" "$PROJECT_PATH/.docker-compose-db.yml" "$PROJECT_PATH/.docker-compose.yml"

  # Buat direktori logs
  mkdir -p "$PROJECT_PATH/logs"

  # ── Deteksi Stack & Dependencies (stack.json) ──────────────────────────────
  log "Mendeteksi stack, runtime, ekstensi, dan dependensi..."
  python3 "$SCRIPTS_DIR/detect_stack.py" "$SRC_DIR" --output "$PROJECT_PATH/stack.json"
  
  # Ambil runtime version dari stack.json jika PHP_VERSION_PARAM kosong
  if [[ -z "$PHP_VERSION_PARAM" ]]; then
    PHP_VERSION="$(python3 -c "import json; d=json.load(open('$PROJECT_PATH/stack.json')); print(d.get('runtime_version', '8.2'))" 2>/dev/null || echo "8.2")"
  else
    PHP_VERSION="$PHP_VERSION_PARAM"
  fi

  if [[ "$(printf '%s\n' "$PHP_VERSION" "7.2" | sort -V | head -n1)" == "$PHP_VERSION" && "$PHP_VERSION" != "7.2" ]]; then
    COMPOSER_VERSION=1
  else
    COMPOSER_VERSION=2
  fi

  hr
  echo " Mode          : MONOLITH (Clean Structure)"
  echo " Project       : $PROJECT_NAME"
  echo " Path          : $PROJECT_PATH"
  echo " Source (src)  : $SRC_DIR"
  echo " Web Server    : Apache"
  echo " HTTP Port     : $HTTP_PORT"
  echo " MySQL Host    : 127.0.0.1 (Data lokal: $SCRIPT_DIR/docker/db/ladock_mysql/data)"
  echo " MySQL Port    : $DB_PORT"
  echo " PHP Version   : $PHP_VERSION"
  echo " Stack Spec    : $PROJECT_PATH/stack.json"
  hr

  # ── Siapkan Folder Database & Backup Lokal ────────────────────────────────
  CENTRAL_DB_DIR="$SCRIPT_DIR/mysql/db/$PROJECT_NAME"
  mkdir -p "$CENTRAL_DB_DIR"

  # Pindahkan dump .sql yang mungkin ada di src/ atau root ke mysql/db/<app_name>/
  find "$SRC_DIR" "$PROJECT_PATH" -maxdepth 2 -type f -name "*.sql" 2>/dev/null | while read -r sql_found; do
    if [[ ! "$sql_found" =~ /mysql/db/ ]]; then
      dest_sql="$CENTRAL_DB_DIR/$(basename "$sql_found")"
      [[ ! -f "$dest_sql" ]] && cp "$sql_found" "$dest_sql" && rm -f "$sql_found" || true
    fi
  done

  # ── Kredensial Database ────────────────────────────────────────────────────
  CREDS_FILE="$PROJECT_PATH/.credentials.env"
  FRESH_DEPLOY=0
  if [[ -f "$CREDS_FILE" ]]; then
    log "Menggunakan kredensial database yang tersimpan..."
    # shellcheck disable=SC1090
    source "$CREDS_FILE"
  else
    log "Men-generate kredensial database baru..."
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
    chmod 600 "$CREDS_FILE"
  fi

  # ── Memastikan Database Sentral Aktif ──────────────────────────────────────
  "$SCRIPT_DIR/central_db.sh" start

  if [[ -f "$CENTRAL_ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CENTRAL_ENV_FILE"
  fi
  CENTRAL_DB_CONTAINER="${LADOCK_DB_CONTAINER:-ladock_mysql}"
  CENTRAL_DB_PORT="${LADOCK_DB_PORT:-3308}"
  CENTRAL_DB_ROOT_PASS="${LADOCK_DB_ROOT_PASS:-3baa6e5d124af02611fd0efb79ae292d}"
  DB_PORT="$CENTRAL_DB_PORT"

  # ── Render File Deployment Bersih di Root Project ─────────────────────────
  log "Menyiapkan file deployment bersih (Dockerfile, apache-vhost.conf, docker-compose.yml)..."
  cp "$TEMPLATE_DIR/Dockerfile" "$PROJECT_PATH/Dockerfile"
  cp "$TEMPLATE_DIR/.dockerignore" "$PROJECT_PATH/.dockerignore"

  DOC_ROOT="/var/www/public"
  if [[ ! -d "$SRC_DIR/public" ]] || [[ -f "$SRC_DIR/index.php" && ! -f "$SRC_DIR/public/index.php" ]]; then
    DOC_ROOT="/var/www"
  fi

  sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
      -e "s|__DOCUMENT_ROOT__|$DOC_ROOT|g" \
      "$TEMPLATE_DIR/apache-vhost.conf.tpl" > "$PROJECT_PATH/apache-vhost.conf"

  sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
      -e "s/__HTTP_PORT__/$HTTP_PORT/g" \
      -e "s/__MEMORY_LIMIT__/$MEMORY_LIMIT/g" \
      -e "s/__DB_NAME__/$DB_NAME/g" \
      -e "s/__DB_USER__/$DB_USER/g" \
      -e "s/__DB_PASS__/$DB_PASS/g" \
      -e "s/__PHP_VERSION__/$PHP_VERSION/g" \
      -e "s/__COMPOSER_VERSION__/$COMPOSER_VERSION/g" \
      "$TEMPLATE_DIR/docker-compose-app.yml.tpl" > "$PROJECT_PATH/docker-compose.yml"

  # ── Konfigurasi .env (tanpa meninggalkan file .env.bak) ────────────────────
  cd "$SRC_DIR"
  if [[ ! -f .env ]]; then
    [[ -f .env.example ]] && cp .env.example .env || touch .env
  fi

  set_clean_env() {
    local key="$1" val="$2" file="$3"
    if grep -q "^${key}=" "$file" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" "$file"
    else
      echo "${key}=${val}" >> "$file"
    fi
  }

  set_clean_env "DB_CONNECTION" "mysql" "$SRC_DIR/.env"
  set_clean_env "DB_HOST"       "$CENTRAL_DB_CONTAINER" "$SRC_DIR/.env"
  set_clean_env "DB_PORT"       "3306" "$SRC_DIR/.env"
  set_clean_env "DB_DATABASE"   "$DB_NAME" "$SRC_DIR/.env"
  set_clean_env "DB_USERNAME"   "$DB_USER" "$SRC_DIR/.env"
  set_clean_env "DB_PASSWORD"   "$DB_PASS" "$SRC_DIR/.env"
  set_clean_env "APP_URL"       "http://localhost:${HTTP_PORT}" "$SRC_DIR/.env"
  set_clean_env "ASSET_URL"     "http://localhost:${HTTP_PORT}" "$SRC_DIR/.env"

  for key in ADMIN_HTTPS FORCE_HTTPS LARAVEL_ADMIN_HTTPS SESSION_SECURE_COOKIE; do
    grep -q "^${key}=" "$SRC_DIR/.env" && set_clean_env "$key" "false" "$SRC_DIR/.env"
  done

  # ── Normalisasi Asset & URL Template ──────────────────────────────────────
  if [[ -f "$SCRIPTS_DIR/normalize_assets.py" ]]; then
    log "Memeriksa dan menormalisasi path URL aset statis lokal..."
    python3 "$SCRIPTS_DIR/normalize_assets.py" "$SRC_DIR" || true
  fi

  # Buat salinan .env di root project untuk kemudahan akses
  cp "$SRC_DIR/.env" "$PROJECT_PATH/.env"

  # ── Sample Config Files untuk Native PHP ──────────────────────────────────
  while IFS= read -r sample_file; do
    [ -z "$sample_file" ] && continue
    target_file="$(echo "$sample_file" | sed -E 's/\.(sample|example)(\.php)?$/\2/; s/\.php\.(sample|example)$/.php/')"
    if [ ! -f "$target_file" ]; then
      cp "$sample_file" "$target_file" || true
    fi

    sed -i \
      -e "s/private \$host = .*/private \$host = \"$CENTRAL_DB_CONTAINER\";/" \
      -e "s/private \$port = .*/private \$port = \"3306\";/" \
      -e "s/private \$db_name = .*/private \$db_name = \"$DB_NAME\";/" \
      -e "s/private \$username = .*/private \$username = \"$DB_USER\";/" \
      -e "s/private \$password = .*/private \$password = \"$DB_PASS\";/" \
      -e "s/\$host = .*/\$host = \"$CENTRAL_DB_CONTAINER\";/" \
      -e "s/\$db_name = .*/\$db_name = \"$DB_NAME\";/" \
      -e "s/\$db_user = .*/\$db_user = \"$DB_USER\";/" \
      -e "s/\$db_pass = .*/\$db_pass = \"$DB_PASS\";/" \
      "$target_file" || true
  done < <(find "$SRC_DIR" -type f \( -name "*.sample.php" -o -name "*.example.php" -o -name "*.php.sample" -o -name "*.php.example" \) 2>/dev/null || true)

  # ── Buat Database & User di DB Sentral ────────────────────────────────────
  log "Memastikan Database '$DB_NAME' & User '$DB_USER' di DB Sentral..."
  docker exec -i "$CENTRAL_DB_CONTAINER" mysql -uroot -p"$CENTRAL_DB_ROOT_PASS" -e "
    CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASS}';
    ALTER USER '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASS}';
    GRANT ALL PRIVILEGES ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';
    FLUSH PRIVILEGES;
  " >/dev/null 2>&1

  log "Membersihkan container App lama jika ada..."
  cd "$PROJECT_PATH"
  $DC -f docker-compose.yml -p "${PROJECT_NAME}_app_stack" down --remove-orphans >/dev/null 2>&1 || true

  log "Build image & menjalankan container App..."
  $DC -f docker-compose.yml -p "${PROJECT_NAME}_app_stack" up -d --build

  # ── Import Dump Database ──────────────────────────────────────────────────
  IS_EMPTY_DB=0
  TABLE_COUNT=$(docker exec -i "$CENTRAL_DB_CONTAINER" mysql -uroot -p"$CENTRAL_DB_ROOT_PASS" -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DB_NAME';" -sN 2>/dev/null || echo "0")
  if [[ "${TABLE_COUNT:-0}" -eq 0 ]]; then
    IS_EMPTY_DB=1
  fi

  SHOULD_IMPORT=0
  [[ $SKIP_IMPORT -eq 0 ]] && { [[ $FRESH_DEPLOY -eq 1 || $FORCE_IMPORT -eq 1 || $IS_EMPTY_DB -eq 1 || -n "$DUMP_FILE" ]] && SHOULD_IMPORT=1; }

  if [[ $SHOULD_IMPORT -eq 1 ]]; then
    log "Memeriksa & mengimpor dump database (.sql) ke DB Sentral..."
    DUMP_ARGS=(
      --project-path "$PROJECT_PATH"
      --project-name "$PROJECT_NAME"
      --db-name      "$DB_NAME"
      --db-root-pass "$CENTRAL_DB_ROOT_PASS"
      --db-container "$CENTRAL_DB_CONTAINER"
      --central-db
    )
    [[ -n "$DUMP_FILE" ]] && DUMP_ARGS+=(--dump "$DUMP_FILE")
    python3 "$SCRIPTS_DIR/db_import.py" "${DUMP_ARGS[@]}"

    # Buat backup dokumentasi dan README di folder mysql/db/<app_name>/
    "$SCRIPTS_DIR/db_dump.sh" "$PROJECT_NAME" "$DB_NAME" "$CENTRAL_DB_DIR" >/dev/null 2>&1 || true
  else
    log "Lewati import dump (database tidak kosong)."
  fi

  # ── Setup Dependency & Framework di dalam Container ───────────────────────
  log "Menyiapkan dependensi dan cache di dalam container..."
  $DC -f docker-compose.yml -p "${PROJECT_NAME}_app_stack" exec -T "app_${PROJECT_NAME}" bash -lc "
    set -e
    if [ -f composer.json ]; then
      if composer install --no-interaction --prefer-dist --optimize-autoloader 2>&1 | tee /tmp/composer_output | grep -q 'does not satisfy'; then
        echo '⚠️  Dependencies tidak kompatibel, menjalankan composer update...'
        composer update --no-interaction --prefer-dist --optimize-autoloader
      fi
    fi
    if [ -f artisan ]; then
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
    fi
  " || true

  echo ""
  hr
  echo " ✓ DEPLOY BERHASIL — Aplikasi '$PROJECT_NAME' sudah aktif!"
  echo " Akses Web    : http://localhost:$HTTP_PORT"
  echo " Lokasi App   : $PROJECT_PATH"
  echo " Source Code  : $SRC_DIR"
  echo " DB Sentral   : 127.0.0.1:$CENTRAL_DB_PORT (Container: $CENTRAL_DB_CONTAINER)"
  echo "   DB Name    : $DB_NAME"
  echo "   DB User    : $DB_USER"
  echo "   DB Pass    : $DB_PASS"
  echo " DB Folder    : $CENTRAL_DB_DIR/"
  echo " Stack Spec   : $PROJECT_PATH/stack.json"
  echo " Logs Folder  : $PROJECT_PATH/logs/"
  hr
  exit 0
fi

# ==============================================================================
# ████████████████████  MODE MICROSERVICE  ███████████████████████████████████
# ==============================================================================

log "Mode MICROSERVICE diaktifkan"

declare -a SVC_NAMES=()
declare -A SVC_PATHS=()

while IFS=$'\t' read -r svc_name svc_path; do
  [[ -z "$svc_name" || -z "$svc_path" ]] && continue
  SVC_NAMES+=("$svc_name")
  SVC_PATHS["$svc_name"]="$svc_path"
done <<< "$MICROSERVICE_LIST_RAW"

if [[ ${#SVC_NAMES[@]} -eq 0 ]]; then
  echo "❌ Tidak ada sub-project Laravel ditemukan di: $PROJECT_PATH"
  exit 1
fi

RAW_NAME="$(basename "$PROJECT_PATH")"
PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
SOURCE_PROJECT_PATH="$PROJECT_PATH"
PROJECT_PATH="$DEFAULT_DEPLOY_ROOT/$PROJECT_NAME"
LEGACY_PROJECT_PATH="$SCRIPT_DIR/docker/$PROJECT_NAME"
if [[ ! -e "$PROJECT_PATH" && -d "$LEGACY_PROJECT_PATH" ]]; then
  log "Memindahkan project microservice lama ke struktur docker/apps/..."
  mkdir -p "$(dirname "$PROJECT_PATH")"
  mv "$LEGACY_PROJECT_PATH" "$PROJECT_PATH"
  for svc_name in "${SVC_NAMES[@]}"; do
    SOURCE_SVC_PATH="${SVC_PATHS[$svc_name]}"
    if [[ "$SOURCE_SVC_PATH" == "$LEGACY_PROJECT_PATH/"* ]]; then
      SVC_PATHS["$svc_name"]="$PROJECT_PATH/${SOURCE_SVC_PATH#"$LEGACY_PROJECT_PATH/"}"
    fi
  done
fi
mkdir -p "$PROJECT_PATH/apps"

for svc_name in "${SVC_NAMES[@]}"; do
  SOURCE_SVC_PATH="${SVC_PATHS[$svc_name]}"
  TARGET_SVC_PATH="$PROJECT_PATH/apps/$svc_name"
  mkdir -p "$TARGET_SVC_PATH"
  if [[ "$(realpath "$SOURCE_SVC_PATH")" != "$(realpath "$TARGET_SVC_PATH")" ]]; then
    log "Menyalin source service '$svc_name' ke $TARGET_SVC_PATH ..."
    cp -a "$SOURCE_SVC_PATH/." "$TARGET_SVC_PATH/"
  fi
  SVC_PATHS["$svc_name"]="$TARGET_SVC_PATH"
done

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

  svc_path="${SVC_PATHS[$svc_name]}"
  # Deteksi stack per service
  python3 "$SCRIPTS_DIR/detect_stack.py" "$svc_path" --output "$svc_path/stack.json" 2>/dev/null || true
  php_ver=$(python3 -c "import json; d=json.load(open('$svc_path/stack.json')); print(d.get('runtime_version', '8.4'))" 2>/dev/null || echo "8.4")
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
echo " Source Root  : $SOURCE_PROJECT_PATH"
echo " Project Name : $PROJECT_NAME"
echo " Gateway Port : $GATEWAY_PORT"
echo " MySQL Port   : $DB_PORT"
echo " Services     : ${#SVC_NAMES[@]}"
for svc_name in "${SVC_NAMES[@]}"; do
  echo "   [$svc_name] PHP ${SVC_PHP_VERSIONS[$svc_name]} | direct :${SVC_HTTP_PORTS[$svc_name]} | route /${svc_name}/"
done
hr

mkdir -p "$PROJECT_PATH/logs"
DOCKER_DIR="$PROJECT_PATH/.docker"
CREDS_DIR="$DOCKER_DIR/credentials"
GATEWAY_DIR="$DOCKER_DIR/gateway"
mkdir -p "$DOCKER_DIR" "$CREDS_DIR" "$GATEWAY_DIR"

ROOT_PASS_FILE="$CREDS_DIR/.db_root_pass"
if [[ -f "$ROOT_PASS_FILE" ]]; then
  DB_ROOT_PASS="$(cat "$ROOT_PASS_FILE")"
else
  DB_ROOT_PASS="$(openssl rand -hex 16)"
  echo "$DB_ROOT_PASS" > "$ROOT_PASS_FILE"
  chmod 600 "$ROOT_PASS_FILE"
fi

FRESH_DEPLOYS=()
for svc_name in "${SVC_NAMES[@]}"; do
  CREDS_FILE="$CREDS_DIR/${svc_name}.env"
  if [[ -f "$CREDS_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$CREDS_FILE"
    SVC_DB_NAMES["$svc_name"]="$DB_NAME"
    SVC_DB_USERS["$svc_name"]="$DB_USER"
    SVC_DB_PASSES["$svc_name"]="$DB_PASS"
  else
    FRESH_DEPLOYS+=("$svc_name")
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

  [[ -n "${SVC_PATHS_ARG:-}" ]] && SVC_PATHS_ARG+=","
  SVC_PATHS_ARG+="${svc_name}:${SVC_PATHS[$svc_name]}"
done

COMPOSE_DB_FILE="$PROJECT_PATH/.docker-compose-db.yml"
COMPOSE_APP_FILE="$PROJECT_PATH/.docker-compose-app.yml"

log "Men-generate docker-compose-db.yml dan docker-compose-app.yml..."
python3 "$SCRIPTS_DIR/generate_compose.py" \
  --project           "$PROJECT_NAME" \
  --services          "$SERVICES_ARG" \
  --service-paths     "${SVC_PATHS_ARG:-}" \
  --docker-dir        "$DOCKER_DIR" \
  --gateway-port      "$GATEWAY_PORT" \
  --db-port           "$DB_PORT" \
  --db-data-root      "$SCRIPT_DIR/docker/db" \
  --memory-limit      "$MEMORY_LIMIT" \
  --db-root-pass      "$DB_ROOT_PASS" \
  --php-versions      "$PHP_VERS_ARG" \
  --composer-versions "$COMP_VERS_ARG" \
  --db-creds          "$DB_CREDS_ARG" \
  --output-dir        "$PROJECT_PATH"

cp "$TEMPLATE_DIR/Dockerfile" "$DOCKER_DIR/Dockerfile"
[[ -f "$TEMPLATE_DIR/.dockerignore" ]] && cp "$TEMPLATE_DIR/.dockerignore" "$PROJECT_PATH/.dockerignore"

DOC_ROOT="/var/www/public"
sed -e "s/__PROJECT__/$PROJECT_NAME/g" \
    -e "s|__DOCUMENT_ROOT__|$DOC_ROOT|g" \
    "$TEMPLATE_DIR/apache-vhost.conf.tpl" > "$DOCKER_DIR/apache-vhost.conf"

GATEWAY_CONF_RAW="$(python3 "$SCRIPTS_DIR/generate_gateway_conf.py" \
  --project "$PROJECT_NAME" \
  --services "$SERVICES_ARG" \
  --gateway-port "$GATEWAY_PORT")"

GATEWAY_CONF="${GATEWAY_CONF_RAW%%# __DASHBOARD_HTML_MARKER__*}"
DASHBOARD_HTML="${GATEWAY_CONF_RAW##*# __DASHBOARD_HTML_MARKER__}"

echo "$GATEWAY_CONF" > "$DOCKER_DIR/apache-gateway.conf"
echo "$DASHBOARD_HTML" > "$GATEWAY_DIR/dashboard.html"
cp "$TEMPLATE_DIR/gateway.Dockerfile" "$GATEWAY_DIR/Dockerfile"
cp "$TEMPLATE_DIR/gateway-httpd.conf" "$GATEWAY_DIR/httpd.conf"

for svc_name in "${SVC_NAMES[@]}"; do
  svc_path="${SVC_PATHS[$svc_name]}"
  db_name="${SVC_DB_NAMES[$svc_name]}"
  db_user="${SVC_DB_USERS[$svc_name]}"
  db_pass="${SVC_DB_PASSES[$svc_name]}"

  cd "$svc_path"
  [[ ! -f .env ]] && ([[ -f .env.example ]] && cp .env.example .env || touch .env)

  set_clean_env() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" .env
    else
      echo "${key}=${val}" >> .env
    fi
  }

  set_clean_env "DB_CONNECTION" "mysql"
  set_clean_env "DB_HOST"       "db_${svc_name}"
  set_clean_env "DB_PORT"       "3306"
  set_clean_env "DB_DATABASE"   "$db_name"
  set_clean_env "DB_USERNAME"   "$db_user"
  set_clean_env "DB_PASSWORD"   "$db_pass"
  set_clean_env "APP_URL"       "http://localhost:${GATEWAY_PORT}/${svc_name}"
done

log "Menjalankan stack microservices..."
cd "$PROJECT_PATH"
$DC -f "$COMPOSE_APP_FILE" -p "${PROJECT_NAME}_app_stack" down --remove-orphans >/dev/null 2>&1 || true
$DC -f "$COMPOSE_DB_FILE" -p "${PROJECT_NAME}_db_stack" down --remove-orphans >/dev/null 2>&1 || true

for svc_name in "${SVC_NAMES[@]}"; do
  DB_PROJECT_DIR="$SCRIPT_DIR/docker/db/$PROJECT_NAME"
  DB_SERVICE_DIR="$DB_PROJECT_DIR/$svc_name"
  DB_DATA_DIR="$DB_SERVICE_DIR/data"
  DB_MIGRATION_MARKER="$DB_SERVICE_DIR/.local-storage-migrated"
  LEGACY_DB_SERVICE_DIR="$PROJECT_PATH/db/$svc_name"
  if [[ ! -d "$LEGACY_DB_SERVICE_DIR" && -d "$LEGACY_PROJECT_PATH/db/$svc_name" ]]; then
    LEGACY_DB_SERVICE_DIR="$LEGACY_PROJECT_PATH/db/$svc_name"
  fi
  if [[ -d "$LEGACY_DB_SERVICE_DIR" ]]; then
    if [[ ! -e "$DB_SERVICE_DIR" ]]; then
      log "Memindahkan data DB service '$svc_name' ke $DB_SERVICE_DIR ..."
      mkdir -p "$DB_PROJECT_DIR"
      mv "$LEGACY_DB_SERVICE_DIR" "$DB_SERVICE_DIR"
    elif [[ -n "$(find "$LEGACY_DB_SERVICE_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      echo "❌ Data DB lama dan baru sama-sama ada untuk '$svc_name'; migrasi dihentikan agar data tidak tertimpa." >&2
      exit 1
    fi
  fi
  OLD_DB_VOLUME="${PROJECT_NAME}_db_stack_${PROJECT_NAME}_${svc_name}_dbdata"
  mkdir -p "$DB_DATA_DIR"

  if docker volume inspect "$OLD_DB_VOLUME" >/dev/null 2>&1; then
    if [[ -f "$DB_MIGRATION_MARKER" ]]; then
      info "Datadir lokal '$svc_name' sudah dimigrasikan; named volume lama dipertahankan sebagai cadangan."
    elif [[ -z "$(find "$DB_DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      log "Memindahkan data DB service '$svc_name' ke $DB_DATA_DIR ..."
      docker run --rm \
        -v "${OLD_DB_VOLUME}:/source:ro" \
        -v "$DB_DATA_DIR:/destination" \
        --user 0:0 \
        --entrypoint sh \
        mysql:8.0 \
        -ec 'cp -a /source/. /destination/'
      touch "$DB_MIGRATION_MARKER"
    else
      echo "❌ Migrasi DB '$svc_name' dibatalkan: folder lokal berisi data tetapi belum memiliki penanda migrasi: $DB_DATA_DIR" >&2
      exit 1
    fi
  fi
done

$DC -f "$COMPOSE_DB_FILE" -p "${PROJECT_NAME}_db_stack" up -d

for svc_name in "${SVC_NAMES[@]}"; do
  timeout=60; elapsed=0
  until $DC -f "$COMPOSE_DB_FILE" -p "${PROJECT_NAME}_db_stack" exec -T "db_${svc_name}" \
        mysql -uroot -p"$DB_ROOT_PASS" -e "SELECT 1" >/dev/null 2>&1; do
    [[ $elapsed -ge $timeout ]] && echo "MySQL db_${svc_name} timeout." && break
    sleep 2; elapsed=$((elapsed+2))
  done
done

$DC -f "$COMPOSE_APP_FILE" -p "${PROJECT_NAME}_app_stack" up -d --build

hr
echo " ✓ MICROSERVICES LIVE — http://localhost:${GATEWAY_PORT}/"
hr