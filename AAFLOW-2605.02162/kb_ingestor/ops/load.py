from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.csv as pacsv
import pyarrow.json as pajson

from kb_ingestor.errors import IngestNullError, IngestSchemaError
from kb_ingestor.models import CANONICAL_TICKET_SCHEMA, IngestConfig


def _null_timestamps(length: int) -> pa.Array:
    return pa.array([None] * length, type=pa.timestamp("us"))


def _to_timestamp(values: pa.Array) -> pa.Array:
    if pa.types.is_timestamp(values.type):
        return pc.cast(values, pa.timestamp("us"))
    text = pc.cast(values, pa.string())
    text = pc.replace_substring(text, "Z", "")
    parsed = pc.strptime(text, format="%Y-%m-%dT%H:%M:%S", unit="us", error_is_null=True)
    return parsed


def _split_tags(tags: pa.Array) -> pa.Array:
    safe_tags = pc.fill_null(tags, "")
    return pc.split_pattern(safe_tags, pattern=",")


def _normalize_zendesk(table: pa.Table) -> pa.Table:
    required = ["id", "subject", "description"]
    missing = [col for col in required if col not in table.column_names]
    if missing:
        raise IngestSchemaError(missing)

    rows = table.num_rows
    status = table.column("status") if "status" in table.column_names else pa.array([None] * rows, type=pa.string())
    created_raw = table.column("created_at") if "created_at" in table.column_names else _null_timestamps(rows)
    tags_raw = table.column("tags") if "tags" in table.column_names else pa.array([None] * rows, type=pa.string())

    normalized = pa.table(
        {
            "id": pc.cast(table.column("id"), pa.string()),
            "subject": pc.cast(table.column("subject"), pa.string()),
            "description": pc.cast(table.column("description"), pa.string()),
            "status": pc.cast(status, pa.string()),
            "created_at": _to_timestamp(created_raw),
            "tags": _split_tags(pc.cast(tags_raw, pa.string())),
            "source": pa.array(["zendesk"] * rows, type=pa.string()),
        },
        schema=CANONICAL_TICKET_SCHEMA,
    )
    return normalized


def _normalize_jira(table: pa.Table) -> pa.Table:
    if "key" not in table.column_names or "fields" not in table.column_names:
        missing = []
        if "key" not in table.column_names:
            missing.append("key")
        if "fields" not in table.column_names:
            missing.append("fields")
        raise IngestSchemaError(missing)

    fields = table.column("fields")
    summary = pc.struct_field(fields, "summary")
    description = pc.struct_field(fields, "description")
    if summary is None or description is None:
        raise IngestSchemaError(["fields.summary", "fields.description"])

    status_struct = pc.struct_field(fields, "status")
    status = pc.struct_field(status_struct, "name") if status_struct is not None else pa.array([None] * table.num_rows, type=pa.string())
    created = pc.struct_field(fields, "created")
    labels = pc.struct_field(fields, "labels")

    if labels is None:
        labels = pa.array([None] * table.num_rows, type=pa.list_(pa.string()))

    normalized = pa.table(
        {
            "id": pc.cast(table.column("key"), pa.string()),
            "subject": pc.cast(summary, pa.string()),
            "description": pc.cast(description, pa.string()),
            "status": pc.cast(status, pa.string()),
            "created_at": _to_timestamp(created),
            "tags": pc.cast(labels, pa.list_(pa.string())),
            "source": pa.array(["jira"] * table.num_rows, type=pa.string()),
        },
        schema=CANONICAL_TICKET_SCHEMA,
    )
    return normalized


def _enforce_null_policy(table: pa.Table, config: IngestConfig) -> pa.Table:
    description = table.column("description")
    is_null = pc.is_null(description)
    is_empty = pc.equal(pc.fill_null(description, ""), "")
    is_bad = pc.or_kleene(is_null, is_empty)
    null_count = pc.sum(pc.cast(is_bad, pa.int32())).as_py()
    if not null_count:
        return table

    if config.null_policy == "raise":
        ids = table.filter(is_bad).column("id").to_pylist()
        raise IngestNullError(ids)

    return table.filter(pc.invert(is_bad))


def _normalize_arrow_table(table: pa.Table, config: IngestConfig) -> pa.Table:
    required = ["id", "subject", "description", "status", "created_at", "tags"]
    missing = [col for col in required if col not in table.column_names]
    if missing:
        raise IngestSchemaError(missing)

    working = table
    if "source" not in working.column_names:
        source = config.source_type if config.source_type in {"zendesk", "jira"} else "unknown"
        working = working.append_column("source", pa.array([source] * working.num_rows, type=pa.string()))

    normalized = pa.table(
        {
            "id": pc.cast(working.column("id"), pa.string()),
            "subject": pc.cast(working.column("subject"), pa.string()),
            "description": pc.cast(working.column("description"), pa.string()),
            "status": pc.cast(working.column("status"), pa.string()),
            "created_at": _to_timestamp(working.column("created_at")),
            "tags": pc.cast(working.column("tags"), pa.list_(pa.string())),
            "source": pc.cast(working.column("source"), pa.string()),
        },
        schema=CANONICAL_TICKET_SCHEMA,
    )
    return normalized


def load(source: Path | pa.Table, config: IngestConfig) -> pa.Table:
    if isinstance(source, pa.Table):
        normalized = _normalize_arrow_table(source, config)
        return _enforce_null_policy(normalized, config)

    source_path = Path(source)
    source_type = config.source_type
    if source_type == "auto":
        if source_path.suffix.lower() == ".csv":
            source_type = "zendesk"
        elif source_path.suffix.lower() == ".json":
            source_type = "jira"
        else:
            raise IngestSchemaError(["source_type:auto unsupported extension"])

    if source_type == "zendesk":
        table = pacsv.read_csv(source_path)
        normalized = _normalize_zendesk(table)
    elif source_type == "jira":
        table = pajson.read_json(source_path)
        normalized = _normalize_jira(table)
    else:
        raise IngestSchemaError([f"unknown source_type: {source_type}"])

    return _enforce_null_policy(normalized, config)
