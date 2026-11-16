#!/usr/bin/env bash
# ==============================================================================
# LaDock Monitor & Control Center - Launcher Script
# Digunakan untuk menjalankan, mematikan, atau mengecek status monitoring dashboard
#
# Penggunaan:
#   ./monitor.sh              -> Jalankan di background (default port 9090)
#   ./monitor.sh start [port] -> Jalankan di background pada port tertentu
#   ./monitor.sh run [port]   -> Jalankan di foreground (interactive terminal)
#   ./monitor.sh stop         -> Hentikan dashboard
#   ./monitor.sh restart      -> Restart dashboard
#   ./monitor.sh status       -> Cek status dashboard
#   ./monitor.sh logs         -> Streaming file log dashboard
#   ./monitor.sh deploy <path1> <path2> ... -> Deploy beberapa project berurutan
#   ./monitor.sh resume [checkpoint-id]    -> Lanjutkan batch deploy yang terhenti
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_UI="$SCRIPT_DIR/scripts/start_ui.sh"

deploy_usage() {
  cat <<EOF
Penggunaan:
  $0 deploy <path-project-1> <path-project-2> [...] [opsi deploy]
  $0 resume [checkpoint-id]

Setiap path folder atau file arsip akan di-deploy berurutan dengan port otomatis.
Checkpoint batch disimpan di logs/deploy-queues; project sukses dilewati saat resume,
sedangkan project yang terputus diulang dari awal.
Opsi yang berlaku untuk semua project:
  --force-import
  --skip-import
  --replace-existing
  --dump=FILE
  --mode=MODE
  --max-depth=N
  --base-app-port=N
  --memory-limit=SIZE
EOF
}

if [[ "${1:-}" == "resume" ]]; then
  shift
  if [[ $# -gt 1 ]]; then
    echo "❌ Masukkan maksimal satu ID checkpoint." >&2
    deploy_usage >&2
    exit 2
  fi
  RESUME_ARGS=(resume --state-dir "$SCRIPT_DIR/logs/deploy-queues")
  [[ -n "${1:-}" ]] && RESUME_ARGS+=(--id "$1")
  exec python3 "$SCRIPT_DIR/scripts/deploy_batch.py" "${RESUME_ARGS[@]}"
fi

if [[ "${1:-}" == "deploy" ]]; then
  shift
  PROJECTS=()
  DEPLOY_OPTIONS=()
  for arg in "$@"; do
    case "$arg" in
      --force-import|--skip-import|--replace-existing|--dump=*|--mode=*|--max-depth=*|--base-app-port=*|--memory-limit=*)
        DEPLOY_OPTIONS+=("$arg")
        ;;
      --help|-h)
        deploy_usage
        exit 0
        ;;
      --*)
        echo "❌ Opsi deploy tidak didukung: $arg" >&2
        deploy_usage >&2
        exit 2
        ;;
      *)
        PROJECTS+=("$arg")
        ;;
    esac
  done

  if [[ ${#PROJECTS[@]} -eq 0 ]]; then
    echo "❌ Masukkan minimal satu path project atau arsip." >&2
    deploy_usage >&2
    exit 2
  fi

  BATCH_ARGS=(
    run-new
    --state-dir "$SCRIPT_DIR/logs/deploy-queues"
    --deploy-script "$SCRIPT_DIR/deploy.sh"
  )
  for project in "${PROJECTS[@]}"; do
    BATCH_ARGS+=("--target=$project")
  done
  for option in "${DEPLOY_OPTIONS[@]}"; do
    BATCH_ARGS+=("--deploy-option=$option")
  done
  exec python3 "$SCRIPT_DIR/scripts/deploy_batch.py" "${BATCH_ARGS[@]}"
fi

if [[ -f "$START_UI" ]]; then
  exec "$START_UI" "$@"
fi

echo "❌ Script $START_UI tidak ditemukan."
exit 1
