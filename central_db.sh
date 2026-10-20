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
VOLUME_NAME="${LADOCK_DB_VOLUME:-ladock_db_central_data}"
LOCAL_DATA_DIR="$SCRIPT_DIR/docker/db/ladock_mysql/data"
LEGACY_LOCAL_DATA_DIR="$SCRIPT_DIR/docker/ladock_mysql/data"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  DC="docker-compose"
fi

log()  { echo "--> $*"; }
info() { echo "    $*"; }

remove_stale_socket_link() {
  local socket_link="$LOCAL_DATA_DIR/mysql.sock"
  if [[ -L "$socket_link" && "$(readlink "$socket_link")" == "/var/run/mysqld/mysqld.sock" ]]; then
    log "Menghapus symlink socket MySQL lama dari datadir lokal..."
    rm -- "$socket_link"
  elif [[ -S "$socket_link" ]]; then
    log "Menghapus file socket MySQL lama dari datadir lokal..."
    rm -- "$socket_link"
  fi
}

ensure_central_db() {
  mkdir -p "$LOCAL_DATA_DIR"

  # 1. Pastikan Docker Network ada
  if ! docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
    log "Membuat Docker Network '$NETWORK_NAME'..."
    docker network create "$NETWORK_NAME" >/dev/null
  fi

  local container_exists=0
  docker inspect "$CONTAINER_NAME" >/dev/null 2>&1 && container_exists=1

  # Migrate an existing container's datadir before recreating it with a bind mount.
  if [[ $container_exists -eq 1 ]]; then
    local mount_type mount_source local_real socket_config_source
    mount_type="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Type}}{{end}}{{end}}' "$CONTAINER_NAME")"
    mount_source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Source}}{{end}}{{end}}' "$CONTAINER_NAME")"
    local_real="$(realpath "$LOCAL_DATA_DIR")"

    if [[ "$mount_type" == "bind" && "$mount_source" == "$local_real" ]]; then
      socket_config_source="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/etc/mysql/conf.d/ladock.cnf"}}{{.Source}}{{end}}{{end}}' "$CONTAINER_NAME")"
      if [[ "$socket_config_source" != "$SCRIPT_DIR/templates/mysql-central.cnf" ]]; then
        log "Memperbarui konfigurasi socket MySQL tanpa memindahkan datadir..."
        if [[ "$(docker inspect --format '{{.State.Running}}' "$CONTAINER_NAME")" == "true" ]]; then
          docker stop "$CONTAINER_NAME" >/dev/null
        fi
        docker rm "$CONTAINER_NAME" >/dev/null
        container_exists=0
        remove_stale_socket_link
      else
        if [[ "$(docker inspect --format '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]]; then
          remove_stale_socket_link
          log "Menyalakan kembali Database Sentral '$CONTAINER_NAME'..."
          docker start "$CONTAINER_NAME" >/dev/null
        else
          info "Database Sentral '$CONTAINER_NAME' sudah berjalan dari $LOCAL_DATA_DIR."
        fi
      fi
    else
      if [[ -n "$(find "$LOCAL_DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
        echo "❌ Migrasi dibatalkan: folder tujuan tidak kosong: $LOCAL_DATA_DIR" >&2
        echo "   Data container lama tidak diubah. Amankan/cek isi folder tujuan terlebih dahulu." >&2
        exit 1
      fi
      if [[ -z "$mount_type" ]]; then
        echo "❌ Container '$CONTAINER_NAME' tidak memiliki mount /var/lib/mysql; migrasi otomatis dihentikan." >&2
        exit 1
      fi

      log "Menyalin data MySQL lama ke folder lokal (container dihentikan sementara)..."
      if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
        docker stop "$CONTAINER_NAME" >/dev/null
      fi

      docker run --rm \
        --volumes-from "${CONTAINER_NAME}:ro" \
        -v "$LOCAL_DATA_DIR:/destination" \
        --user 0:0 \
        --entrypoint sh \
        mysql:8.0 \
        -ec 'cp -a /var/lib/mysql/. /destination/'

      # Keep the old named volume intact as a rollback copy.
      docker rm "$CONTAINER_NAME" >/dev/null
    fi
  elif [[ -z "$(find "$LOCAL_DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] && \
       docker volume inspect "$VOLUME_NAME" >/dev/null 2>&1; then
    log "Menyalin data dari Docker volume '$VOLUME_NAME' ke folder lokal..."
    docker run --rm \
      -v "${VOLUME_NAME}:/source:ro" \
      -v "$LOCAL_DATA_DIR:/destination" \
      --user 0:0 \
      --entrypoint sh \
      mysql:8.0 \
      -ec 'cp -a /source/. /destination/'
  fi

  if [[ -d "$LEGACY_LOCAL_DATA_DIR" ]] && \
     [[ -n "$(find "$LEGACY_LOCAL_DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]] && \
     [[ -z "$(find "$LOCAL_DATA_DIR" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    log "Menyalin datadir MySQL lokal lama ke '$LOCAL_DATA_DIR'..."
    cp -a "$LEGACY_LOCAL_DATA_DIR/." "$LOCAL_DATA_DIR/"
  fi

  # 2. Ensure the central database container uses local project storage.
  if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    remove_stale_socket_link
    log "Menjalankan Database Sentral MySQL baru ('$CONTAINER_NAME') pada port $DB_PORT..."
    docker run -d \
      --name "$CONTAINER_NAME" \
      --restart unless-stopped \
      --network "$NETWORK_NAME" \
      -p "${DB_PORT}:3306" \
      -v "$LOCAL_DATA_DIR:/var/lib/mysql" \
      -v "$SCRIPT_DIR/templates/mysql-central.cnf:/etc/mysql/conf.d/ladock.cnf:ro" \
      -e MYSQL_ROOT_PASSWORD="$ROOT_PASS" \
      mysql:8.0 \
      --default-authentication-plugin=mysql_native_password >/dev/null
  fi

  # 3. Wait until MySQL is ready
  info "Menunggu Database Sentral siap..."
  timeout=60; elapsed=0
  until docker exec -i "$CONTAINER_NAME" mysqladmin ping -h localhost -uroot -p"$ROOT_PASS" --silent >/dev/null 2>&1; do
    if [[ $elapsed -ge $timeout ]]; then
      echo "❌ DB Sentral tidak siap dalam $timeout detik. Log container '$CONTAINER_NAME':" >&2
      docker logs --tail 80 "$CONTAINER_NAME" >&2 || true
      exit 1
    fi
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
