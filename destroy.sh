#!/usr/bin/env bash
set -euo pipefail

# ============================================================
#  Laravel Docker Auto-Deploy - Cleanup
#  Usage: ./destroy.sh /path/to/laravel-project [--with-images]
# ============================================================

PROJECT_PATH="${1:-}"
FLAG="${2:-}"

if [[ -z "$PROJECT_PATH" ]]; then
  echo "Usage: $0 /path/to/laravel-project [--with-images]"
  exit 1
fi

PROJECT_PATH="$(cd "$PROJECT_PATH" && pwd)"
RAW_NAME="$(basename "$PROJECT_PATH")"
PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
COMPOSE_FILE="$PROJECT_PATH/.docker-compose.yml"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Tidak ditemukan .docker-compose.yml di $PROJECT_PATH (project belum pernah di-deploy dengan script ini?)"
  exit 1
fi

echo "-> Menghentikan & menghapus container + volume DB project '$PROJECT_NAME'..."
cd "$PROJECT_PATH"
$DC -f "$COMPOSE_FILE" -p "$PROJECT_NAME" down -v --remove-orphans

if [[ "$FLAG" == "--with-images" ]]; then
  echo "-> Menghapus image terkait project ini..."
  docker images --filter "reference=${PROJECT_NAME}*" -q | xargs -r docker rmi -f
fi

echo "Cleanup selesai untuk '$PROJECT_NAME'."