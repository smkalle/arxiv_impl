"""
Central configuration for EvolveMem TicketMind v2.0.
All paths, env vars, and pre-flight checks live here.
"""
import os
import subprocess
import sys
from pathlib import Path

# ── Project root ────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()

# ── Data paths ──────────────────────────────────────────────────────────────
DATA_DIR        = ROOT / "data"
RAW_DIR         = DATA_DIR / "raw"
LANCEDB_DIR     = DATA_DIR / "lancedb"
LOOP_STATES_DIR = DATA_DIR / "loop_states"
EVOLVED_DIR     = DATA_DIR / "evolved"
LOGS_DIR        = ROOT / "logs"

KB_ARTICLES_CSV     = RAW_DIR / "kb_articles.csv"
RESOLVED_TICKETS_CSV = RAW_DIR / "resolved_tickets.csv"
DEV_SET_JSON        = DATA_DIR / "dev_set.json"
TEST_SET_JSON       = DATA_DIR / "test_set.json"
FAILURE_LOG_JSONL   = DATA_DIR / "failure_log.jsonl"

EVOLVED_DEV_SET_CONFIG   = EVOLVED_DIR / "dev_set_config.json"
EVOLVED_INGESTOR_CONFIG  = EVOLVED_DIR / "ingestor_config.json"
EVOLVED_RETRIEVAL_CONFIG = EVOLVED_DIR / "retrieval_config.json"
EVOLVED_DIAGNOSIS_PROMPT = EVOLVED_DIR / "diagnosis_prompt.txt"

L1_STATE = LOOP_STATES_DIR / "l1_state.json"
L2_STATE = LOOP_STATES_DIR / "l2_state.json"
L3_STATE = LOOP_STATES_DIR / "l3_state.json"
L4_STATE = LOOP_STATES_DIR / "l4_state.json"

# ── SimpleMem ────────────────────────────────────────────────────────────────
SIMPLEMEM_DIR = ROOT / "SimpleMem"

# ── API ──────────────────────────────────────────────────────────────────────
API_HOST = os.environ.get("EVOLVEMEM_API_HOST", "0.0.0.0")
API_PORT = int(os.environ.get("EVOLVEMEM_API_PORT", "8001"))
DASHBOARD_HOST = os.environ.get("EVOLVEMEM_DASH_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.environ.get("EVOLVEMEM_DASH_PORT", "8000"))

# ── LLM provider ─────────────────────────────────────────────────────────────
# Set DIAGNOSIS_LLM_PROVIDER=anthropic (default) or ollama
DIAGNOSIS_LLM_PROVIDER = os.environ.get("DIAGNOSIS_LLM_PROVIDER", "anthropic")
ANTHROPIC_API_KEY       = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL         = os.environ.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
OLLAMA_URL              = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL            = os.environ.get("OLLAMA_MODEL", "llama3")

# ── Latency guard ────────────────────────────────────────────────────────────
MAX_QUERY_LATENCY_MS = 600  # P95 budget; enforced by meta_analyzer

# ── Dev set defaults (overridden by L1 evolution) ───────────────────────────
DEV_SET_DEFAULTS = {
    "min_csat": 4,
    "n_train": 150,
    "n_test": 50,
    "vocab_gap_ratio": 0.0,
    "augmentation_strategy": "none",
}

# ── Ingestor defaults (overridden by L2 evolution) ──────────────────────────
SIMPLEMEM_USE_STUB = os.environ.get("SIMPLEMEM_USE_STUB", "true").lower() in ("1", "true", "yes")

INGESTOR_DEFAULTS = {
    "chunk_strategy": "paragraph",
    "max_chunk_tokens": 400,
    "min_chunk_chars": 20,
    "chunk_overlap": 50,
    "max_parallel_workers": 4,
    "add_product_area_entity": False,
}

# ── Ensure runtime directories exist ─────────────────────────────────────────
for _d in [LANCEDB_DIR, LOOP_STATES_DIR, EVOLVED_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


def check_ext4(path: Path = LANCEDB_DIR) -> bool:
    """Return True if path is on an ext4 filesystem."""
    try:
        result = subprocess.run(
            ["df", "-T", str(path)],
            capture_output=True, text=True, timeout=5,
        )
        return "ext4" in result.stdout
    except Exception:
        return False  # non-Linux / df unavailable — skip check


def preflight(require_ext4: bool = False) -> None:
    """Run pre-flight checks. Call before starting any loop."""
    if sys.version_info < (3, 10):
        raise RuntimeError(f"Python 3.10+ required, got {sys.version}")

    if require_ext4 and not check_ext4():
        raise RuntimeError(
            f"LanceDB path {LANCEDB_DIR} must be on ext4 filesystem. "
            "Run 'df -T' to verify."
        )

    if DIAGNOSIS_LLM_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. "
            "Set it or switch DIAGNOSIS_LLM_PROVIDER=ollama."
        )
