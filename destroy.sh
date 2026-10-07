#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Laravel Docker Auto-Deploy — Cleanup
#  Mendukung mode Monolith & Microservice secara otomatis.
#
#  Usage:
#    ./destroy.sh /path/to/project [--with-images]
#
#  Mode Monolith : project-path langsung adalah folder Laravel
#  Mode Microservice : project-path adalah folder root yang berisi sub-services
# ============================================================

PROJECT_PATH="${1:-}"
WITH_IMAGES=0

for arg in "${@:2}"; do
  [[ "$arg" == "--with-images" ]] && WITH_IMAGES=1
done

if [[ -z "$PROJECT_PATH" ]]; then
  echo "Usage: $0 /path/to/project [--with-images]"
  exit 1
fi

PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"
RAW_NAME="$(basename "$PROJECT_PATH")"
PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
COMPOSE_DB_FILE="$PROJECT_PATH/.docker-compose-db.yml"
COMPOSE_APP_FILE="$PROJECT_PATH/.docker-compose-app.yml"
OLD_COMPOSE_FILE="$PROJECT_PATH/.docker-compose.yml"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

if [[ ! -f "$COMPOSE_DB_FILE" && ! -f "$COMPOSE_APP_FILE" && ! -f "$OLD_COMPOSE_FILE" ]]; then
  echo "Tidak ditemukan file .docker-compose-*.yml di $PROJECT_PATH"
  echo "(Project belum pernah di-deploy dengan script ini?)"
  exit 1
fi

echo "--> Menghentikan container project '$PROJECT_NAME'..."
cd "$PROJECT_PATH"

if [[ -f "$COMPOSE_APP_FILE" ]]; then
  $DC -f "$COMPOSE_APP_FILE" -p "${PROJECT_NAME}_app_stack" down --remove-orphans >/dev/null 2>&1 || true
fi
if [[ -f "$COMPOSE_DB_FILE" ]]; then
  $DC -f "$COMPOSE_DB_FILE" -p "${PROJECT_NAME}_db_stack" down --remove-orphans >/dev/null 2>&1 || true
fi
if [[ -f "$OLD_COMPOSE_FILE" ]]; then
  $DC -f "$OLD_COMPOSE_FILE" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
fi

if [[ $WITH_IMAGES -eq 1 ]]; then
  echo "--> Menghapus image terkait project ini..."
  docker images --filter "reference=${PROJECT_NAME}*" -q | xargs -r docker rmi -f 2>/dev/null || true
  docker images --filter "reference=*${PROJECT_NAME}*" -q | xargs -r docker rmi -f 2>/dev/null || true
fi

# ── Hapus file generated di .docker/ ─────────────────────────────────────────
DOCKER_DIR="$PROJECT_PATH/.docker"
if [[ -d "$DOCKER_DIR" ]]; then
  echo "--> Menghapus file konfigurasi Docker yang di-generate ($DOCKER_DIR)..."
  rm -rf "$DOCKER_DIR/apache-vhost.conf"
  rm -rf "$DOCKER_DIR/apache-gateway.conf"
  rm -rf "$DOCKER_DIR/Dockerfile"
  rm -rf "$DOCKER_DIR/gateway"
  # Hapus credentials jika --with-images (cleanup total)
  if [[ $WITH_IMAGES -eq 1 ]]; then
    echo "--> Menghapus kredensial database..."
    rm -rf "$DOCKER_DIR/credentials"
    rmdir "$DOCKER_DIR" 2>/dev/null || true
  fi
fi

# Hapus .docker-compose-*.yml di root project
rm -f "$COMPOSE_DB_FILE" "$COMPOSE_APP_FILE" "$OLD_COMPOSE_FILE"

echo "Cleanup selesai untuk '$PROJECT_NAME'."