from __future__ import annotations

import dataclasses
import os
from pathlib import Path
from typing import Any

from sira_kb_ingestor.models import IngestAndRetrieveConfig


def discover_config_path(cwd: Path | None = None, home: Path | None = None) -> Path | None:
    base = cwd or Path.cwd()
    candidate = base / ".sira-ingest.toml"
    if candidate.exists():
        return candidate

    home_dir = home or Path.home()
    fallback = home_dir / ".config" / "sira-ingest" / "config.toml"
    if fallback.exists():
        return fallback
    return None


def _read_toml(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    # Minimal TOML reader for v0.1 needs (sections + scalar key/value).
    data: dict[str, Any] = {}
    section: str | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            data.setdefault(section, {})
            continue
        if "=" not in line:
            continue
        key, raw_val = [part.strip() for part in line.split("=", 1)]
        val: Any
        if raw_val.startswith(("'", '"')) and raw_val.endswith(("'", '"')):
            val = raw_val[1:-1]
        else:
            lowered = raw_val.lower()
            if lowered in {"true", "false"}:
                val = lowered == "true"
            else:
                try:
                    val = int(raw_val)
                except ValueError:
                    try:
                        val = float(raw_val)
                    except ValueError:
                        val = raw_val
        if section is None:
            data[key] = val
        else:
            assert isinstance(data[section], dict)
            data[section][key] = val
    return data


def _flatten_config_dict(data: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key in ("ingest", "enrichment", "retrieval", "output", "server"):
        section = data.get(key, {})
        if isinstance(section, dict):
            flattened.update(section)
    for k, v in data.items():
        if not isinstance(v, dict):
            flattened[k] = v
    return flattened


def _env_config(env: dict[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    out: dict[str, Any] = {}
    mapping: dict[str, tuple[str, type]] = {
        "SIRA_INGEST_BATCH_SIZE": ("batch_size", int),
        "SIRA_INGEST_MAX_WORKERS": ("max_workers", int),
        "SIRA_INGEST_EMBED_MODEL": ("embed_model", str),
        "SIRA_INGEST_ENRICHMENT_MODEL": ("enrichment_model", str),
        "SIRA_INGEST_TAU": ("tau", float),
        "SIRA_INGEST_WEIGHT": ("weight", float),
        "SIRA_INGEST_TOP_K": ("top_k", int),
        "SIRA_INGEST_OLLAMA_HOST": ("ollama_host", str),
    }
    for env_key, (field, cast) in mapping.items():
        if env_key in source:
            out[field] = cast(source[env_key])
    return out


def merge_config(
    cli_overrides: dict[str, Any] | None = None,
    file_config: dict[str, Any] | None = None,
    env_config: dict[str, Any] | None = None,
) -> IngestAndRetrieveConfig:
    merged: dict[str, Any] = {}
    if env_config:
        merged.update(env_config)
    if file_config:
        merged.update(file_config)
    if cli_overrides:
        merged.update({k: v for k, v in cli_overrides.items() if v is not None})

    if "output_path" in merged and isinstance(merged["output_path"], str):
        merged["output_path"] = Path(merged["output_path"])
    if "path" in merged and "output_path" not in merged:
        output_path = merged.pop("path")
        merged["output_path"] = Path(output_path) if isinstance(output_path, str) else output_path
    valid_fields = {field.name for field in dataclasses.fields(IngestAndRetrieveConfig)}
    merged = {k: v for k, v in merged.items() if k in valid_fields}
    return IngestAndRetrieveConfig(**merged)


def load_config(
    cli_overrides: dict[str, Any] | None = None,
    config_path: Path | None = None,
    cwd: Path | None = None,
    home: Path | None = None,
    env: dict[str, str] | None = None,
) -> IngestAndRetrieveConfig:
    path = config_path or discover_config_path(cwd=cwd, home=home)
    file_data = _flatten_config_dict(_read_toml(path))
    env_data = _env_config(env)
    return merge_config(cli_overrides=cli_overrides, file_config=file_data, env_config=env_data)
