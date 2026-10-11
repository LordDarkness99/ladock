#!/usr/bin/env bash
# ==============================================================================
# LaDock — Start UI Control Center & Web Dashboard
# Launcher untuk menjalankan server web dashboard dan control center
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
SERVER_JS="$ROOT_DIR/monitor/server.js"
SERVER_PY="$ROOT_DIR/monitor/server.py"
PID_FILE="/tmp/ladock_monitor.pid"
LOG_FILE="/tmp/ladock_monitor.log"
DEFAULT_PORT=9090

# Cek runtime
RUNNER=""
if command -v node >/dev/null 2>&1; then
  RUNNER="node $SERVER_JS"
elif command -v python3 >/dev/null 2>&1; then
  RUNNER="python3 $SERVER_PY"
else
  echo "❌ Node.js atau Python 3 tidak ditemukan!"
  exit 1
fi

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  if pgrep -f "(node.*monitor/server.js|python3.*monitor/server.py)" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

start_bg() {
  local port="${1:-$DEFAULT_PORT}"
  if is_running; then
    echo "⚠️  Dashboard sudah berjalan!"
    status
    return 0
  fi

  echo "--> Menjalankan LaDock Control Center di port $port..."
  PORT="$port" setsid -f $RUNNER </dev/null > "$LOG_FILE" 2>&1
  sleep 1

  local new_pid
  new_pid="$(pgrep -f "(node.*monitor/server.js|python3.*monitor/server.py)" | head -n1 || echo "")"
  [[ -n "$new_pid" ]] && echo "$new_pid" > "$PID_FILE"

  if is_running; then
    echo "======================================================"
    echo "  ✓ LaDock Control Center AKTIF!"
    echo "  Akses Web : http://localhost:$port"
    echo "  PID       : $new_pid"
    echo "  Log       : $LOG_FILE"
    echo "======================================================"
  else
    echo "❌ Gagal menjalankan dashboard. Cek log:"
    cat "$LOG_FILE"
    exit 1
  fi
}

run_fg() {
  local port="${1:-$DEFAULT_PORT}"
  if is_running; then
    stop
  fi
  echo "--> Menjalankan LaDock Control Center di foreground (port $port)..."
  PORT="$port" exec $RUNNER
}

stop() {
  echo "--> Menghentikan LaDock Control Center..."
  local stopped=0
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      stopped=1
    fi
    rm -f "$PID_FILE"
  fi

  pkill -f "(node.*monitor/server.js|python3.*monitor/server.py)" 2>/dev/null && stopped=1 || true

  if [[ $stopped -eq 1 ]]; then
    echo "✓ Dashboard berhasil dihentikan."
  else
    echo "ℹ️  Dashboard tidak sedang berjalan."
  fi
}

status() {
  if is_running; then
    local pid="Unknown"
    [[ -f "$PID_FILE" ]] && pid="$(cat "$PID_FILE")"
    echo "● LaDock Control Center sedang BERJALAN (PID: $pid)"
    echo "  URL: http://localhost:$DEFAULT_PORT"
  else
    echo "○ LaDock Control Center TIDAK aktif."
    echo "  Jalankan: ./scripts/start_ui.sh start"
  fi
}

CMD="${1:-start}"
case "$CMD" in
  start)   start_bg "${2:-$DEFAULT_PORT}" ;;
  run)     run_fg "${2:-$DEFAULT_PORT}" ;;
  stop)    stop ;;
  restart) stop; sleep 1; start_bg "${2:-$DEFAULT_PORT}" ;;
  status)  status ;;
  logs)    [[ -f "$LOG_FILE" ]] && tail -f -n 50 "$LOG_FILE" || echo "Log belum ada." ;;
  *)       echo "Usage: $0 {start|run|stop|restart|status|logs} [port]"; exit 1 ;;
esac
