#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/.api_server.pid"
LOG_FILE="${ROOT_DIR}/.api_server.log"
HOST="${API_HOST:-0.0.0.0}"
PORT="${API_PORT:-8001}"

if [[ -f "${PID_FILE}" ]]; then
  OLD_PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "${OLD_PID}" 2>/dev/null; then
    echo "API server already running (pid ${OLD_PID})"
    echo "URL: http://localhost:${PORT}/docs"
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

cd "${ROOT_DIR}"
PYTHONPATH=. nohup python3 -m uvicorn src.api:app --host "${HOST}" --port "${PORT}" > "${LOG_FILE}" 2>&1 < /dev/null &
NEW_PID=$!
echo "${NEW_PID}" > "${PID_FILE}"

for _ in {1..20}; do
  if curl -s -o /dev/null "http://127.0.0.1:${PORT}/health"; then
    echo "API server started (pid ${NEW_PID})"
    echo "URL: http://localhost:${PORT}/docs"
    echo "Health: http://localhost:${PORT}/health"
    echo "Log: ${LOG_FILE}"
    exit 0
  fi
  sleep 0.5
done

echo "API server failed to start. Recent logs:"
tail -n 40 "${LOG_FILE}" || true
exit 1
