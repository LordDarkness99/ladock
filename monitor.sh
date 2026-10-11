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
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_UI="$SCRIPT_DIR/scripts/start_ui.sh"

if [[ -f "$START_UI" ]]; then
  exec "$START_UI" "$@"
fi

echo "❌ Script $START_UI tidak ditemukan."
exit 1
