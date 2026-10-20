#!/usr/bin/env bash
set -euo pipefail
trap 'echo "❌ [DESTROY ERROR] Terjadi kegagalan di baris $LINENO!" >&2' ERR

# ==============================================================================
#  LaDock — Cleanup & Destroy
#  Mendukung nama aplikasi langsung atau path folder:
#    ./destroy.sh <app_name_or_path> [--with-images]
#
#  Contoh:
#    ./destroy.sh jatimfair2022
#    ./destroy.sh docker/apps/jatimfair2022
#    ./destroy.sh /home/nizar/Documents/.../app_name
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"
DEFAULT_DEPLOY_ROOT="$SCRIPT_DIR/docker/apps"
if [[ -f "$CONFIG_FILE" ]] && command -v python3 >/dev/null 2>&1; then
  DEFAULT_DEPLOY_ROOT="$(python3 -c "import json, os; d=json.load(open('$CONFIG_FILE')); r=d.get('deploy_root', '$DEFAULT_DEPLOY_ROOT'); print(os.path.abspath(os.path.join('$SCRIPT_DIR', r)) if not os.path.isabs(r) else r)" 2>/dev/null || echo "$DEFAULT_DEPLOY_ROOT")"
fi

INPUT_PATH="${1:-}"
WITH_IMAGES=0

for arg in "${@:2}"; do
  [[ "$arg" == "--with-images" ]] && WITH_IMAGES=1
done

if [[ -z "$INPUT_PATH" ]]; then
  echo "Usage: $0 <app_name_or_path> [--with-images]"
  echo ""
  echo "Contoh:"
  echo "  $0 jatimfair2022"
  echo "  $0 docker/apps/jatimfair2022"
  echo "  $0 /path/ke/folder-project"
  exit 1
fi

# ── Resolusi Direktori Project ────────────────────────────────────────────────
PROJECT_PATH=""
RAW_NAME="$(basename "$INPUT_PATH")"

if [[ -d "$INPUT_PATH" ]]; then
  PROJECT_PATH="$(cd "$INPUT_PATH" && pwd)"
  RAW_NAME="$(basename "$PROJECT_PATH")"
else
  # Cek jika nama ada di folder deployment lokal
  CLEAN_GUESS="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
  STRIPPED_GUESS="${CLEAN_GUESS%_laravel}"
  
  if [[ -d "$DEFAULT_DEPLOY_ROOT/$CLEAN_GUESS" ]]; then
    PROJECT_PATH="$DEFAULT_DEPLOY_ROOT/$CLEAN_GUESS"
    RAW_NAME="$CLEAN_GUESS"
  elif [[ -d "$DEFAULT_DEPLOY_ROOT/$STRIPPED_GUESS" ]]; then
    PROJECT_PATH="$DEFAULT_DEPLOY_ROOT/$STRIPPED_GUESS"
    RAW_NAME="$STRIPPED_GUESS"
  elif [[ -d "$DEFAULT_DEPLOY_ROOT/$RAW_NAME" ]]; then
    PROJECT_PATH="$DEFAULT_DEPLOY_ROOT/$RAW_NAME"
  elif [[ -d "$SCRIPT_DIR/docker/$CLEAN_GUESS" ]]; then
    PROJECT_PATH="$SCRIPT_DIR/docker/$CLEAN_GUESS"
    RAW_NAME="$CLEAN_GUESS"
  elif [[ -d "$SCRIPT_DIR/docker/$STRIPPED_GUESS" ]]; then
    PROJECT_PATH="$SCRIPT_DIR/docker/$STRIPPED_GUESS"
    RAW_NAME="$STRIPPED_GUESS"
  fi
fi

PROJECT_NAME="$(echo "$RAW_NAME" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g' | sed -E 's/^_+|_+$//g')"
PROJECT_NAME="${PROJECT_NAME%_laravel}"

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

echo "--> Menghentikan & membersihkan container untuk project '$PROJECT_NAME'..."

# 1. Hentikan via Docker Compose jika folder dan file compose ditemukan
if [[ -n "$PROJECT_PATH" && -d "$PROJECT_PATH" ]]; then
  cd "$PROJECT_PATH"
  for compose_file in "docker-compose.yml" ".docker-compose-app.yml" ".docker-compose-db.yml" ".docker-compose.yml"; do
    if [[ -f "$compose_file" ]]; then
      $DC -f "$compose_file" -p "${PROJECT_NAME}_app_stack" down --remove-orphans >/dev/null 2>&1 || true
      $DC -f "$compose_file" -p "${PROJECT_NAME}_db_stack" down --remove-orphans >/dev/null 2>&1 || true
      $DC -f "$compose_file" -p "$PROJECT_NAME" down --remove-orphans >/dev/null 2>&1 || true
    fi
  done
fi

# 2. Hentikan container langsung berdasarkan nama jika compose down terlewat
CONTAINER_NAMES=(
  "${PROJECT_NAME}_app"
  "app_${PROJECT_NAME}"
  "${PROJECT_NAME}_gateway"
  "gateway_${PROJECT_NAME}"
)

for cname in "${CONTAINER_NAMES[@]}"; do
  if docker ps -a --format '{{.Names}}' | grep -q "^${cname}$"; then
    echo "    Menghentikan container $cname..."
    docker stop "$cname" >/dev/null 2>&1 || true
    docker rm "$cname" >/dev/null 2>&1 || true
  fi
done

# 3. Hapus image jika diminta
if [[ $WITH_IMAGES -eq 1 ]]; then
  echo "--> Menghapus Docker image terkait project ini..."
  docker images --filter "reference=*${PROJECT_NAME}*" -q | xargs -r docker rmi -f 2>/dev/null || true
fi

# 4. Hapus file-file generated sementara jika --with-images
if [[ $WITH_IMAGES -eq 1 && -n "$PROJECT_PATH" && -d "$PROJECT_PATH" ]]; then
  rm -f "$PROJECT_PATH/Dockerfile" "$PROJECT_PATH/apache-vhost.conf" "$PROJECT_PATH/docker-compose.yml"
  rm -f "$PROJECT_PATH/.dockerignore" "$PROJECT_PATH/.credentials.env"
  rm -rf "$PROJECT_PATH/.docker"
fi

echo "✓ Selesai: Container untuk '$PROJECT_NAME' berhasil dihentikan dan dibersihkan."