from pathlib import Path

import pyarrow as pa
import pytest

from kb_ingestor.errors import IngestNullError, IngestSchemaError
from kb_ingestor.models import IngestConfig
from kb_ingestor.ops.load import load


def test_load_zendesk_csv(tmp_path: Path) -> None:
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text(
        "id,subject,description,status,created_at,tags\n"
        "1,Login issue,Cannot sign in,open,2026-01-01T10:00:00Z,auth\n"
        "2,Page error,500 error on dashboard,closed,2026-01-02T11:00:00Z,web\n",
        encoding="utf-8",
    )

    table = load(csv_path, IngestConfig())
    assert table.num_rows == 2
    assert table.column_names == ["id", "subject", "description", "status", "created_at", "tags", "source"]
    assert table.column("source").to_pylist() == ["zendesk", "zendesk"]


def test_load_jira_json(tmp_path: Path) -> None:
    json_path = tmp_path / "issues.json"
    json_path.write_text(
        '{"key":"J-1","fields":{"summary":"Login fail","description":"Cannot authenticate","status":{"name":"Open"},"created":"2026-01-01T10:00:00Z","labels":["auth","prod"]}}\n'
        '{"key":"J-2","fields":{"summary":"UI bug","description":"Button overlaps text","status":{"name":"Done"},"created":"2026-01-02T10:00:00Z","labels":["ui"]}}\n',
        encoding="utf-8",
    )

    table = load(json_path, IngestConfig())
    assert table.num_rows == 2
    assert table.column("id").to_pylist() == ["J-1", "J-2"]
    assert table.column("source").to_pylist() == ["jira", "jira"]


def test_load_arrow_table() -> None:
    table = pa.table(
        {
            "id": ["1"],
            "subject": ["Subject"],
            "description": ["Desc"],
            "status": ["open"],
            "created_at": ["2026-01-01T10:00:00Z"],
            "tags": [["a", "b"]],
        }
    )
    result = load(table, IngestConfig(source_type="zendesk"))
    assert result.num_rows == 1
    assert result.column("source").to_pylist() == ["zendesk"]


def test_null_policy_drop(tmp_path: Path) -> None:
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text(
        "id,subject,description,status\n"
        "1,ok,hello,open\n"
        "2,bad,,open\n",
        encoding="utf-8",
    )

    result = load(csv_path, IngestConfig(null_policy="drop"))
    assert result.num_rows == 1
    assert result.column("id").to_pylist() == ["1"]


def test_null_policy_raise(tmp_path: Path) -> None:
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text(
        "id,subject,description,status\n"
        "1,ok,hello,open\n"
        "2,bad,,open\n",
        encoding="utf-8",
    )

    with pytest.raises(IngestNullError):
        load(csv_path, IngestConfig(null_policy="raise"))


def test_load_missing_required_columns_raises(tmp_path: Path) -> None:
    csv_path = tmp_path / "bad.csv"
    csv_path.write_text("id,subject\n1,only\n", encoding="utf-8")
    with pytest.raises(IngestSchemaError):
        load(csv_path, IngestConfig())
