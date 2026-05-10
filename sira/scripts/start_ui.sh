#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/.ui_server.pid"
LOG_FILE="${ROOT_DIR}/.ui_server.log"
HOST="${UI_HOST:-0.0.0.0}"
PORT="${UI_PORT:-8000}"

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" 2>/dev/null; then
    echo "UI server already running (pid ${OLD_PID})"
    echo "URL: http://localhost:${PORT}/query"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

cd "${ROOT_DIR}"
nohup python3 -m uvicorn src.enrich_ui:app --host "${HOST}" --port "${PORT}" > "${LOG_FILE}" 2>&1 < /dev/null &
NEW_PID=$!
echo "${NEW_PID}" > "${PID_FILE}"

for _ in {1..20}; do
  if curl -s -o /dev/null "http://127.0.0.1:${PORT}/query"; then
    echo "UI server started (pid ${NEW_PID})"
    echo "URL: http://localhost:${PORT}/query"
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  sleep 0.5
done

echo "UI server failed to start. Recent logs:"
tail -n 40 "${LOG_FILE}" || true
exit 1
