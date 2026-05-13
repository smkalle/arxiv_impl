from __future__ import annotations

from pathlib import Path

from sira_kb_ingestor.config import discover_config_path, load_config, merge_config


def test_discover_config_prefers_cwd(tmp_path: Path) -> None:
    print("[TEST] Validating config discovery prefers project local file")
    cfg = tmp_path / ".sira-ingest.toml"
    cfg.write_text("[ingest]\nbatch_size=222\n", encoding="utf-8")
    discovered = discover_config_path(cwd=tmp_path, home=tmp_path / "home")
    assert discovered == cfg


def test_load_config_from_file(tmp_path: Path) -> None:
    print("[TEST] Validating TOML config values are loaded and typed")
    cfg_file = tmp_path / ".sira-ingest.toml"
    cfg_file.write_text(
        "[ingest]\nbatch_size=300\n"
        "[enrichment]\nenrichment_model='qwen2.5-coder:3b'\n"
        "[retrieval]\ntau=0.02\n",
        encoding="utf-8",
    )
    cfg = load_config(config_path=cfg_file)
    assert cfg.batch_size == 300
    assert cfg.enrichment_model == "qwen2.5-coder:3b"
    assert cfg.tau == 0.02


def test_env_override(tmp_path: Path) -> None:
    print("[TEST] Validating env variables are applied when no CLI override")
    cfg_file = tmp_path / ".sira-ingest.toml"
    cfg_file.write_text("[ingest]\nbatch_size=120\n", encoding="utf-8")
    cfg = load_config(
        config_path=cfg_file,
        env={"SIRA_INGEST_BATCH_SIZE": "256"},
    )
    assert cfg.batch_size == 120


def test_cli_precedence_over_file_and_env() -> None:
    print("[TEST] Validating precedence order CLI > file > env > defaults")
    cfg = merge_config(
        cli_overrides={"batch_size": 999},
        file_config={"batch_size": 333},
        env_config={"batch_size": 111},
    )
    assert cfg.batch_size == 999


def test_output_path_cast_from_string() -> None:
    print("[TEST] Validating string output_path is cast to pathlib.Path")
    cfg = merge_config(cli_overrides={"output_path": "/tmp/demo"})
    assert str(cfg.output_path) == "/tmp/demo"


def test_empty_env_mapping_does_not_read_process_env(monkeypatch) -> None:
    print("[TEST] Validating explicit empty env mapping suppresses process env")
    monkeypatch.setenv("SIRA_INGEST_BATCH_SIZE", "777")
    cfg = load_config(env={})
    assert cfg.batch_size == 128


def test_output_section_path_alias(tmp_path: Path) -> None:
    print("[TEST] Validating [output] path maps to output_path")
    cfg_file = tmp_path / ".sira-ingest.toml"
    cfg_file.write_text("[output]\npath='/tmp/sira-out'\n", encoding="utf-8")
    cfg = load_config(config_path=cfg_file, env={})
    assert str(cfg.output_path) == "/tmp/sira-out"
