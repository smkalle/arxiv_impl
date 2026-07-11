#!/usr/bin/env bash
# test_services.sh — smoke-test the running SIRA services via curl + python3.
#
# Checks both FastAPI apps:
#   API (8001): GET /health, GET /docs, POST /retrieve, POST /feedback
#   UI  (8000): GET /query, GET /api/monitor, GET /api/models, GET /api/articles,
#               POST /api/query (plain + sira modes)
#
# If the services are not reachable, starts them via start_services.sh.
# JSON assertions run in python3 (no jq needed). SIRA mode tolerates sketch
# fallback (Ollama optional). Exits 0 only if all checks pass.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPTS_DIR="${ROOT_DIR}/scripts"
cd "${ROOT_DIR}"

API_PORT="${API_PORT:-8001}"
UI_PORT="${UI_PORT:-8000}"
API="http://127.0.0.1:${API_PORT}"
UI="http://127.0.0.1:${UI_PORT}"

PASS=0; FAIL=0
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

pass() { printf 'PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf 'FAIL: %s — %s\n' "$1" "$2"; FAIL=$((FAIL + 1)); }

# --- ensure services are up (auto-start if down) ---
if ! curl -sf --max-time 3 -o /dev/null "$API/health" 2>/dev/null \
   || ! curl -sf --max-time 3 -o /dev/null "$UI/query" 2>/dev/null; then
  echo "Services not reachable; starting via start_services.sh..."
  bash "${SCRIPTS_DIR}/start_services.sh" start || { echo "ERROR: could not start services" >&2; exit 2; }
  for _ in $(seq 1 12); do
    if curl -sf --max-time 2 -o /dev/null "$API/health" 2>/dev/null \
       && curl -sf --max-time 2 -o /dev/null "$UI/query" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
fi

# --- helpers ---
# assert_http NAME CURL_ARGS...            -> expects HTTP 200
# assert_json NAME PY_EXPR CURL_ARGS...    -> expects 200 + valid JSON + PY_EXPR true (j = parsed body)
assert_http() {
  local name="$1"; shift
  local code
  code=$(curl -s --max-time 30 -o "$TMP" -w '%{http_code}' "$@" 2>/dev/null || true)
  if [[ "$code" == "200" ]]; then pass "$name"; else fail "$name" "http=${code}"; fi
}
assert_json() {
  local name="$1" expr="$2"; shift 2
  local code
  code=$(curl -s --max-time 30 -o "$TMP" -w '%{http_code}' "$@" 2>/dev/null || true)
  if [[ "$code" == "200" ]] \
     && python3 -c "import json,sys; j=json.load(open(sys.argv[1])); assert ${expr}" "$TMP" 2>/dev/null; then
    pass "$name"
  else
    fail "$name" "http=${code} body=$(head -c 160 "$TMP" | tr -d '\n')"
  fi
}

# --- checks ---
assert_json "API GET /health (index loaded, corpus>0)" \
  "j['bm25_index_loaded'] is True and j['corpus_size'] > 0" "$API/health"

assert_http "API GET /docs (swagger UI)" "$API/docs"

assert_json "API POST /retrieve (results list + latency_ms)" \
  "isinstance(j['results'], list) and 'latency_ms' in j and 'fallback_used' in j" \
  -X POST "$API/retrieve" -H 'Content-Type: application/json' \
  -d '{"ticket_id":"t1","ticket_text":"my app keeps crashing on login"}'

assert_http "UI GET /query (HTML page)" "$UI/query"

assert_json "UI GET /api/monitor (health block)" \
  "'health' in j and 'bm25_index_loaded' in j['health'] and 'models' in j" "$UI/api/monitor"

assert_json "UI GET /api/models (installed/missing/rejected keys)" \
  "{'installed','missing','rejected'} <= set(j)" "$UI/api/models"

assert_json "UI GET /api/articles (list + stats)" \
  "isinstance(j['articles'], list) and 'stats' in j" "$UI/api/articles"

assert_json "UI POST /api/query plain (mode=plain, results list)" \
  "j.get('mode') == 'plain' and isinstance(j['results'], list)" \
  -X POST "$UI/api/query" -H 'Content-Type: application/json' \
  -d '{"ticket_text":"app keeps crashing","mode":"plain","top_k":5}'

assert_json "UI POST /api/query sira (results + fallback_used; ollama optional)" \
  "isinstance(j['results'], list) and 'fallback_used' in j" \
  -X POST "$UI/api/query" -H 'Content-Type: application/json' \
  -d '{"ticket_text":"my app keeps crashing on login","mode":"sira","top_k":5}'

assert_json "API POST /feedback (ok=true)" \
  "j.get('ok') is True" \
  -X POST "$API/feedback" -H 'Content-Type: application/json' \
  -d '{"ticket_id":"t1","selected_article_id":"kb-001","rating":5,"comments":"smoke test"}'

# --- summary ---
total=$((PASS + FAIL))
echo
echo "==========================================="
echo " Results: ${PASS} passed, ${FAIL} failed  (of ${total})"
echo "==========================================="
echo "Services still running. Stop with: bash scripts/start_services.sh stop"

exit $(( FAIL > 0 ? 1 : 0 ))
