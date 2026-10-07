#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  LaDock — Script Pengelola Database Sentral (Central MySQL)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.ladock_db.env"

if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
fi

CONTAINER_NAME="${LADOCK_DB_CONTAINER:-ladock_mysql}"
DB_PORT="${LADOCK_DB_PORT:-3308}"
ROOT_PASS="${LADOCK_DB_ROOT_PASS:-3baa6e5d124af02611fd0efb79ae292d}"
NETWORK_NAME="${LADOCK_NET:-ladock_net}"
VOLUME_NAME="ladock_db_central_data"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC="docker-compose"
fi

log()  { echo "--> $*"; }
info() { echo "    $*"; }

ensure_central_db() {
  # 1. Pastikan Docker Network ada
  if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    log "Membuat Docker Network '$NETWORK_NAME'..."
    docker network create "$NETWORK_NAME" >/dev/null
  fi

  # 2. Pastikan Container DB Sentral Berjalan
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    info "Database Sentral '$CONTAINER_NAME' sudah berjalan."
    return 0
  fi

  if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Menyalakan kembali Database Sentral '$CONTAINER_NAME'..."
    docker start "$CONTAINER_NAME" >/dev/null
  else
    log "Menjalankan Database Sentral MySQL baru ('$CONTAINER_NAME') pada port $DB_PORT..."
    docker run -d \
      --name "$CONTAINER_NAME" \
      --restart unless-stopped \
      --network "$NETWORK_NAME" \
      -p "${DB_PORT}:3306" \
      -v "${VOLUME_NAME}:/var/lib/mysql" \
      -e MYSQL_ROOT_PASSWORD="$ROOT_PASS" \
      mysql:8.0 \
      --default-authentication-plugin=mysql_native_password >/dev/null
  fi

  # 3. Tunggu MySQL Siap
  info "Menunggu Database Sentral siap..."
  timeout=60; elapsed=0
  until docker exec -i "$CONTAINER_NAME" mysqladmin ping -h localhost -uroot -p"$ROOT_PASS" --silent >/dev/null 2>&1; do
    [[ $elapsed -ge $timeout ]] && echo "DB Sentral tidak siap dalam $timeout detik." && exit 1
    sleep 2; elapsed=$((elapsed+2))
  done
  log "Database Sentral MySQL ('$CONTAINER_NAME') SIAP!"
}

case "${1:-start}" in
  start)
    ensure_central_db
    ;;
  stop)
    log "Menghentikan Database Sentral '$CONTAINER_NAME'..."
    docker stop "$CONTAINER_NAME" 2>/dev/null || true
    ;;
  status)
    docker ps --filter "name=$CONTAINER_NAME"
    ;;
  *)
    echo "Usage: $0 {start|stop|status}"
    exit 1
    ;;
esac
