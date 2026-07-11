#!/usr/bin/env bash
# start_services.sh — start/stop/restart/status for both SIRA FastAPI services.
#   API (src/api.py)       : port 8001  (env: API_PORT, API_HOST)
#   UI  (src/enrich_ui.py) : port 8000  (env: UI_PORT, UI_HOST)
#
# Delegates to the existing per-service start/stop scripts (pid files + health
# wait logic live there). Run from anywhere; resolves ROOT_DIR from this path.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="${ROOT_DIR}/scripts"
export API_PORT="${API_PORT:-8001}"
export UI_PORT="${UI_PORT:-8000}"

usage() { echo "Usage: $(basename "$0") {start|stop|restart|status}" >&2; exit 2; }

cmd="${1:-start}"
case "$cmd" in
  start)
    echo "Starting SIRA services (API :${API_PORT}, UI :${UI_PORT})..."
    bash "${SCRIPTS_DIR}/start_api.sh"
    bash "${SCRIPTS_DIR}/start_ui.sh"
    echo
    echo "SIRA services running:"
    echo "  API : http://localhost:${API_PORT}/health  (docs: /docs, retrieve: POST /retrieve)"
    echo "  UI  : http://localhost:${UI_PORT}/query    (monitor: /api/monitor)"
    echo "Stop with: bash scripts/start_services.sh stop"
    ;;
  stop)
    bash "${SCRIPTS_DIR}/stop_api.sh" || true
    bash "${SCRIPTS_DIR}/stop_ui.sh" || true
    echo "SIRA services stopped."
    ;;
  restart)
    bash "${SCRIPTS_DIR}/stop_api.sh" || true
    bash "${SCRIPTS_DIR}/stop_ui.sh" || true
    bash "${BASH_SOURCE[0]}" start
    ;;
  status)
    api_pid="$(cat "${ROOT_DIR}/.api_server.pid" 2>/dev/null || true)"
    ui_pid="$(cat "${ROOT_DIR}/.ui_server.pid" 2>/dev/null || true)"
    api_state="down"; ui_state="down"
    if [[ -n "$api_pid" ]] && kill -0 "$api_pid" 2>/dev/null \
       && curl -sf --max-time 3 -o /dev/null "http://127.0.0.1:${API_PORT}/health"; then
      api_state="up (pid ${api_pid})"
    fi
    if [[ -n "$ui_pid" ]] && kill -0 "$ui_pid" 2>/dev/null \
       && curl -sf --max-time 3 -o /dev/null "http://127.0.0.1:${UI_PORT}/query"; then
      ui_state="up (pid ${ui_pid})"
    fi
    echo "API : ${api_state}"
    echo "UI  : ${ui_state}"
    ;;
  *)
    usage
    ;;
esac
