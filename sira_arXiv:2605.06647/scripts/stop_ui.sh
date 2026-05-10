#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${ROOT_DIR}/.ui_server.pid"

if [[ ! -f "${PID_FILE}" ]]; then
  echo "UI server is not running (no pid file)."
  exit 0
fi

PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
if [[ -z "${PID}" ]]; then
  rm -f "${PID_FILE}"
  echo "Removed empty pid file."
  exit 0
fi

if kill -0 "${PID}" 2>/dev/null; then
  kill "${PID}" || true
  for _ in {1..20}; do
    if ! kill -0 "${PID}" 2>/dev/null; then
      rm -f "${PID_FILE}"
      echo "UI server stopped (pid ${PID})."
      exit 0
    fi
    sleep 0.2
  done
  kill -9 "${PID}" || true
fi

rm -f "${PID_FILE}"
echo "UI server stopped."
