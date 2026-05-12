from __future__ import annotations

import json
import random
from pathlib import Path


def _text(i: int) -> str:
    if i % 50 == 0:
        return "これは日本語のサポート説明です。ログインが失敗します。"
    if i % 33 == 0:
        return "هذا وصف عربي لمشكلة في تسجيل الدخول والتوثيق."
    return f"Ticket description number {i} with reproducible issue details for validation."


def generate(out_dir: Path, rows: int = 1000, seed: int = 7) -> None:
    random.seed(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    null_count = int(rows * 0.05)
    null_ids = set(random.sample(range(rows), null_count))

    csv_path = out_dir / "zendesk_1k.csv"
    with csv_path.open("w", encoding="utf-8") as f:
        f.write("id,subject,description,status,created_at,tags\n")
        for i in range(rows):
            desc = "" if i in null_ids else _text(i)
            f.write(f"Z-{i},Subject {i},{desc},open,2026-01-01T10:00:00Z,tag{i%10}\n")

    json_path = out_dir / "jira_1k.json"
    with json_path.open("w", encoding="utf-8") as f:
        for i in range(rows):
            desc = None if i in null_ids else _text(i)
            obj = {
                "key": f"J-{i}",
                "fields": {
                    "summary": f"Summary {i}",
                    "description": desc,
                    "status": {"name": "Open"},
                    "created": "2026-01-01T10:00:00Z",
                    "labels": [f"tag{i%10}"],
                },
            }
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    generate(root / "fixtures")
