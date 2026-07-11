"""Small JSON-backed cross-session memory store."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SESSION_PATH = Path("data/session_store.json")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read(path: Path = DEFAULT_SESSION_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"sessions": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write(data: dict[str, Any], path: Path = DEFAULT_SESSION_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def start_session(customer_id: str, path: Path = DEFAULT_SESSION_PATH) -> dict[str, Any]:
    data = _read(path)
    session_id = str(uuid.uuid4())
    session = {"session_id": session_id, "customer_id": customer_id, "started_at": now_iso(), "events": [], "ended_at": None}
    data["sessions"][session_id] = session
    _write(data, path)
    return session


def record_event(session_id: str, text: str, path: Path = DEFAULT_SESSION_PATH) -> dict[str, Any]:
    data = _read(path)
    session = data["sessions"][session_id]
    event = {"text": text, "recorded_at": now_iso()}
    session["events"].append(event)
    _write(data, path)
    return event


def end_session(session_id: str, path: Path = DEFAULT_SESSION_PATH) -> dict[str, Any]:
    data = _read(path)
    session = data["sessions"][session_id]
    session["ended_at"] = now_iso()
    _write(data, path)
    return session


def list_sessions(path: Path = DEFAULT_SESSION_PATH) -> list[dict[str, Any]]:
    return list(_read(path).get("sessions", {}).values())
