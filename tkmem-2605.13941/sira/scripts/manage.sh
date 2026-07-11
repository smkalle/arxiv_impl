#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

RUNTIME_DIR="${RUNTIME_DIR:-data/run}"
LOG_DIR="${LOG_DIR:-logs}"
API_HOST="${API_HOST:-127.0.0.1}"
API_PORT="${API_PORT:-8001}"
DASHBOARD_HOST="${DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8000}"

mkdir -p "$RUNTIME_DIR" "$LOG_DIR"

usage() {
  cat <<'USAGE'
TicketMind/TKMEM management script
Target: arXiv 2605.13941, EvolveMem/TKMEM-style retrieval evolution.

Usage:
  scripts/manage.sh <command> [args]

Commands:
  install        Install Python dependencies from requirements.txt
  enrich         Build data/enriched_corpus.jsonl from data/kb_corpus.jsonl
  index          Build data/bm25_index.pkl and data/df_store.json
  build          Run enrich + index
  eval           Run retrieval evaluation into data/eval_report.json
  test           Run pytest
  query "text"   Run TKMEM/EvolveMem-style CLI query
  evolve         Run compatibility evolution and write state/config
  paper          Print the target paper and implementation framing
  start          Start API and dashboard in background
  stop           Stop background API and dashboard
  restart        Stop then start services
  status         Show artifact and service status
  logs [svc]     Tail logs. svc: api, dashboard, or all
  smoke          Run health/query/dashboard HTTP smoke checks
  clean          Remove generated runtime artifacts

Environment:
  API_HOST=127.0.0.1 API_PORT=8001 DASHBOARD_HOST=127.0.0.1 DASHBOARD_PORT=8000
USAGE
}

pid_file() {
  echo "$RUNTIME_DIR/$1.pid"
}

is_running() {
  local pid_file_path="$1"
  [[ -f "$pid_file_path" ]] && kill -0 "$(cat "$pid_file_path")" 2>/dev/null
}

start_service() {
  local name="$1"
  local app="$2"
  local host="$3"
  local port="$4"
  local pid_path
  pid_path="$(pid_file "$name")"

  if is_running "$pid_path"; then
    echo "$name already running pid=$(cat "$pid_path")"
    return
  fi

  if command -v setsid >/dev/null 2>&1; then
    setsid python3 -m uvicorn "$app" --host "$host" --port "$port" \
      >"$LOG_DIR/$name.log" 2>&1 < /dev/null &
  else
    nohup python3 -m uvicorn "$app" --host "$host" --port "$port" \
      >"$LOG_DIR/$name.log" 2>&1 < /dev/null &
  fi
  echo "$!" >"$pid_path"
  sleep 0.3
  if is_running "$pid_path"; then
    echo "started $name pid=$(cat "$pid_path") url=http://$host:$port"
  else
    echo "failed to start $name; log follows:" >&2
    sed -n '1,120p' "$LOG_DIR/$name.log" >&2 || true
    rm -f "$pid_path"
    exit 1
  fi
}

stop_service() {
  local name="$1"
  local pid_path
  pid_path="$(pid_file "$name")"

  if ! [[ -f "$pid_path" ]]; then
    echo "$name not running"
    return
  fi

  local pid
  pid="$(cat "$pid_path")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
    echo "stopped $name pid=$pid"
  else
    echo "$name pid file was stale pid=$pid"
  fi
  rm -f "$pid_path"
}

service_status() {
  local name="$1"
  local pid_path
  pid_path="$(pid_file "$name")"
  if is_running "$pid_path"; then
    echo "$name=running pid=$(cat "$pid_path")"
  else
    echo "$name=stopped"
  fi
}

require_curl() {
  if ! command -v curl >/dev/null 2>&1; then
    echo "curl is required for smoke checks" >&2
    exit 1
  fi
}

wait_for_url() {
  local url="$1"
  local attempts="${2:-20}"
  for _ in $(seq 1 "$attempts"); do
    if curl -sS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.25
  done
  echo "timed out waiting for $url" >&2
  return 1
}

cmd="${1:-help}"
shift || true

case "$cmd" in
  install)
    python3 -m pip install -r requirements.txt
    ;;
  enrich)
    python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
    ;;
  index)
    python3 src/index.py data/enriched_corpus.jsonl --output data/bm25_index.pkl
    ;;
  build)
    "$0" enrich
    "$0" index
    ;;
  eval)
    python3 src/evaluate.py \
      --test-set data/annotated_test_set.jsonl \
      --index data/bm25_index.pkl \
      --report data/eval_report.json
    ;;
  test)
    python3 -m pytest tests/
    ;;
  query)
    if [[ $# -lt 1 ]]; then
      echo 'query requires text, e.g. scripts/manage.sh query "app keeps crashing"' >&2
      exit 1
    fi
    python3 scripts/query.py --evolved "$*"
    ;;
  evolve)
    python3 -c "from src.evolution import run_evolution; s=run_evolution(); print(s['mode'], s['post_evolution_f1_at_5'], s['relative_gain'])"
    ;;
  paper)
    cat <<'PAPER'
Target paper: arXiv 2605.13941
Implementation framing: TKMEM/EvolveMem-style retrieval evolution.
Local baseline: BM25 + enrichment/sketch retrieval for runnable validation.
Compatibility: --sira remains a legacy alias; use --evolved for current flows.
PAPER
    ;;
  start)
    start_service api src.ticket_api:app "$API_HOST" "$API_PORT"
    start_service dashboard src.enrich_ui:app "$DASHBOARD_HOST" "$DASHBOARD_PORT"
    ;;
  stop)
    stop_service api
    stop_service dashboard
    ;;
  restart)
    "$0" stop
    "$0" start
    ;;
  status)
    python3 scripts/ops_status.py
    service_status api
    service_status dashboard
    ;;
  logs)
    svc="${1:-all}"
    case "$svc" in
      api) tail -n 80 -f "$LOG_DIR/api.log" ;;
      dashboard) tail -n 80 -f "$LOG_DIR/dashboard.log" ;;
      all) tail -n 80 -f "$LOG_DIR/api.log" "$LOG_DIR/dashboard.log" ;;
      *) echo "unknown log target: $svc" >&2; exit 1 ;;
    esac
    ;;
  smoke)
    require_curl
    wait_for_url "http://$API_HOST:$API_PORT/health"
    wait_for_url "http://$DASHBOARD_HOST:$DASHBOARD_PORT/"
    curl -sS "http://$API_HOST:$API_PORT/health" >/tmp/ticketmind-health.json
    curl -sS -X POST "http://$API_HOST:$API_PORT/query" \
      -H 'Content-Type: application/json' \
      -d '{"ticket":"app keeps crashing on login","use_evolved":true,"top_k":3}' \
      >/tmp/ticketmind-query.json
    curl -sS "http://$DASHBOARD_HOST:$DASHBOARD_PORT/" | grep -q "Query Inspector"
    curl -sS "http://$DASHBOARD_HOST:$DASHBOARD_PORT/kb" | grep -q "KB Browser"
    echo "smoke=ok"
    echo "api_health=/tmp/ticketmind-health.json"
    echo "api_query=/tmp/ticketmind-query.json"
    ;;
  clean)
    rm -f data/bm25_index.pkl data/df_store.json data/enriched_corpus*.jsonl
    rm -f data/eval_report.json data/evolution_state.json data/evolved_config.json data/session_store.json
    rm -rf "$RUNTIME_DIR"
    echo "removed generated artifacts"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
