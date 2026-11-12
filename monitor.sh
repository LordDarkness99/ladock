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
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_UI="$SCRIPT_DIR/scripts/start_ui.sh"

deploy_usage() {
  cat <<EOF
Penggunaan:
  $0 deploy <path-project-1> <path-project-2> [...] [opsi deploy]

Setiap path folder atau file arsip akan di-deploy berurutan dengan port otomatis.
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

  SUCCEEDED=0
  FAILED=0
  for index in "${!PROJECTS[@]}"; do
    project="${PROJECTS[$index]}"
    echo
    echo "[$((index + 1))/${#PROJECTS[@]}] Deploy: $project"
    if bash "$SCRIPT_DIR/deploy.sh" "$project" "${DEPLOY_OPTIONS[@]}"; then
      ((SUCCEEDED += 1))
    else
      ((FAILED += 1))
      echo "❌ Deployment gagal: $project" >&2
    fi
  done

  echo
  echo "Antrean selesai: $SUCCEEDED berhasil, $FAILED gagal."
  if (( FAILED > 0 )); then
    exit 1
  fi
  exit 0
fi

if [[ -f "$START_UI" ]]; then
  exec "$START_UI" "$@"
fi

echo "❌ Script $START_UI tidak ditemukan."
exit 1
