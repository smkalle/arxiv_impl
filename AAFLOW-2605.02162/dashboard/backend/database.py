"""
SQLite database initialization for kb-ingestor admin dashboard.
WAL mode enabled. All tables and indexes created per spec §8.
"""
import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).parent / "kb_admin.db"
_lock = threading.Lock()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS runs (
            run_id          TEXT PRIMARY KEY,
            source_filename TEXT NOT NULL,
            source_type     TEXT NOT NULL,
            config_id       TEXT,
            index_name      TEXT NOT NULL,
            status          TEXT NOT NULL,
            triggered_by    TEXT NOT NULL,
            trigger_type    TEXT NOT NULL,
            rows_total      INTEGER,
            rows_ingested   INTEGER,
            rows_failed     INTEGER,
            batch_size      INTEGER NOT NULL,
            max_workers     INTEGER NOT NULL,
            embed_model     TEXT NOT NULL,
            max_chunk_chars INTEGER NOT NULL,
            null_policy     TEXT NOT NULL,
            append_mode     INTEGER NOT NULL DEFAULT 0,
            t_load_ms       INTEGER,
            t_preprocess_ms INTEGER,
            t_embed_ms      INTEGER,
            t_upsert_ms     INTEGER,
            t_total_ms      INTEGER,
            baseline_t_ms   INTEGER,
            speedup_x       REAL,
            success_rate    REAL,
            artifact_arrow  TEXT,
            artifact_faiss  TEXT,
            artifact_summary TEXT,
            artifact_failed_rows TEXT,
            error_summary   TEXT,
            queued_at       TEXT NOT NULL,
            started_at      TEXT,
            completed_at    TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_runs_status       ON runs (status);
        CREATE INDEX IF NOT EXISTS idx_runs_index_name   ON runs (index_name);
        CREATE INDEX IF NOT EXISTS idx_runs_completed_at ON runs (completed_at DESC);

        CREATE TABLE IF NOT EXISTS batches (
            batch_id        TEXT NOT NULL,
            run_id          TEXT NOT NULL REFERENCES runs(run_id),
            batch_index     INTEGER NOT NULL,
            rows            INTEGER NOT NULL,
            status          TEXT NOT NULL,
            embed_duration_ms INTEGER,
            error_class     TEXT,
            error_message   TEXT,
            error_stack     TEXT,
            affected_row_ids TEXT,
            started_at      TEXT,
            completed_at    TEXT,
            PRIMARY KEY (batch_id, run_id)
        );
        CREATE INDEX IF NOT EXISTS idx_batches_run_id ON batches (run_id);
        CREATE INDEX IF NOT EXISTS idx_batches_status ON batches (run_id, status);

        CREATE TABLE IF NOT EXISTS indexes (
            index_name          TEXT PRIMARY KEY,
            doc_count           INTEGER NOT NULL DEFAULT 0,
            embed_dim           INTEGER NOT NULL,
            embed_model         TEXT NOT NULL,
            last_updated        TEXT NOT NULL,
            size_bytes_arrow    INTEGER,
            size_bytes_faiss    INTEGER,
            artifact_dir        TEXT NOT NULL,
            consistency_status  TEXT NOT NULL DEFAULT 'unchecked',
            consistency_checked_at TEXT,
            soft_deleted        INTEGER NOT NULL DEFAULT 0,
            soft_deleted_at     TEXT,
            soft_deleted_by     TEXT
        );

        CREATE TABLE IF NOT EXISTS run_events (
            event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id      TEXT NOT NULL REFERENCES runs(run_id),
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_run_events_run_id      ON run_events (run_id);
        CREATE INDEX IF NOT EXISTS idx_run_events_recorded_at ON run_events (recorded_at DESC);

        CREATE TABLE IF NOT EXISTS configs (
            config_id       TEXT PRIMARY KEY,
            config_name     TEXT NOT NULL UNIQUE,
            source_type     TEXT,
            batch_size      INTEGER NOT NULL DEFAULT 128,
            max_workers     INTEGER NOT NULL DEFAULT 4,
            max_chunk_chars INTEGER NOT NULL DEFAULT 512,
            min_chunk_chars INTEGER NOT NULL DEFAULT 20,
            null_policy     TEXT NOT NULL DEFAULT 'drop',
            faiss_factory   TEXT NOT NULL DEFAULT 'Flat',
            embed_model     TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
            created_by      TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            updated_at      TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            username        TEXT PRIMARY KEY,
            password_hash   TEXT NOT NULL,
            role            TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            last_login      TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            username    TEXT NOT NULL,
            action      TEXT NOT NULL,
            target_type TEXT,
            target_id   TEXT,
            detail      TEXT,
            ip_address  TEXT,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_log_username    ON audit_log (username);
        CREATE INDEX IF NOT EXISTS idx_audit_log_action      ON audit_log (action);
        CREATE INDEX IF NOT EXISTS idx_audit_log_recorded_at ON audit_log (recorded_at DESC);
    """)

    conn.commit()
    conn.close()


def write_with_lock(fn):
    """Decorator: serialize all write operations through a module-level lock."""
    def wrapper(*args, **kwargs):
        with _lock:
            return fn(*args, **kwargs)
    return wrapper
