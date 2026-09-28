#!/usr/bin/env bash
# ==============================================================================
# LaDock Monitor - Launcher Script
# Digunakan untuk menjalankan, mematikan, atau mengecek status monitoring dashboard
#
# Penggunaan:
#   ./monitor.sh              -> Jalankan di background (default port 9090)
#   ./monitor.sh start [port] -> Jalankan di background pada port tertentu
#   ./monitor.sh run [port]   -> Jalankan di foreground (interactive terminal)
#   ./monitor.sh stop         -> Hentikan dashboard
#   ./monitor.sh restart      -> Restart dashboard
#   ./monitor.sh status       -> Cek status dashboard
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_SCRIPT="$SCRIPT_DIR/monitor/server.py"
PID_FILE="/tmp/ladock_monitor.pid"
LOG_FILE="/tmp/ladock_monitor.log"
DEFAULT_PORT=9090

# Warna output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
      return 0
    fi
  fi
  # Fallback cek process
  if pgrep -f "python3.*monitor/server.py" >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

start_bg() {
  local port="${1:-$DEFAULT_PORT}"

  if is_running; then
    echo -e "${YELLOW}Dashboard sudah berjalan!${NC}"
    status
    return 0
  fi

  echo -e "${CYAN}--> Menjalankan LaDock Monitoring Dashboard di port $port...${NC}"
  setsid -f python3 -u "$SERVER_SCRIPT" "$port" </dev/null > "$LOG_FILE" 2>&1
  sleep 1
  local new_pid
  new_pid="$(pgrep -f "python3.*monitor/server.py $port" | head -n1 || echo "")"
  [[ -n "$new_pid" ]] && echo "$new_pid" > "$PID_FILE"

  if is_running; then
    echo -e "${GREEN}======================================================${NC}"
    echo -e "${GREEN}  LaDock Monitoring Dashboard BERHASIL AKTIF!${NC}"
    echo -e "  Akses Web   : ${CYAN}http://localhost:$port${NC}"
    echo -e "  PID         : $new_pid"
    echo -e "  Log file    : $LOG_FILE"
    echo -e "${GREEN}======================================================${NC}"
    echo -e "Untuk menghentikan: ${YELLOW}./monitor.sh stop${NC}\n"
  else
    echo -e "${RED}Gagal menjalankan dashboard. Cek log:${NC}"
    cat "$LOG_FILE"
    exit 1
  fi
}

run_fg() {
  local port="${1:-$DEFAULT_PORT}"
  if is_running; then
    echo -e "${YELLOW}Menghentikan instance background yang sudah ada...${NC}"
    stop
  fi
  echo -e "${CYAN}--> Menjalankan LaDock Monitor di foreground (port $port)...${NC}"
  exec python3 "$SERVER_SCRIPT" "$port"
}

stop() {
  echo -e "${CYAN}--> Menghentikan LaDock Monitoring Dashboard...${NC}"
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

  # Bersihkan proses jika masih ada
  pkill -f "python3.*monitor/server.py" 2>/dev/null && stopped=1 || true

  if [[ $stopped -eq 1 ]]; then
    echo -e "${GREEN}Dashboard berhasil dihentikan.${NC}"
  else
    echo -e "${YELLOW}Dashboard tidak sedang berjalan.${NC}"
  fi
}

status() {
  if is_running; then
    local pid="Unknown"
    [[ -f "$PID_FILE" ]] && pid="$(cat "$PID_FILE")"
    echo -e "${GREEN}● LaDock Monitor sedang BERJALAN (PID: $pid)${NC}"
    # Cari port dari lsof jika ada
    local port
    port="$(lsof -Pan -p "$pid" -i 2>/dev/null | grep LISTEN | awk '{print $9}' | cut -d: -f2 | head -n1 || echo "$DEFAULT_PORT")"
    [[ -z "$port" ]] && port="$DEFAULT_PORT"
    echo -e "  URL: ${CYAN}http://localhost:$port${NC}"
  else
    echo -e "${RED}○ LaDock Monitor TIDAK aktif.${NC}"
    echo -e "  Jalankan: ${CYAN}./monitor.sh${NC}"
  fi
}

# ── Router Perintah ───────────────────────────────────────────────────────────
CMD="${1:-start}"
case "$CMD" in
  start)
    start_bg "$2"
    ;;
  run)
    run_fg "$2"
    ;;
  stop)
    stop
    ;;
  restart)
    stop
    sleep 1
    start_bg "$2"
    ;;
  status)
    status
    ;;
  logs)
    if [[ -f "$LOG_FILE" ]]; then
      tail -f -n 50 "$LOG_FILE"
    else
      echo "File log belum ada."
    fi
    ;;
  *)
    echo "Penggunaan: $0 {start|run|stop|restart|status|logs} [port]"
    exit 1
    ;;
esac
