from pathlib import Path

from sira_kb_ingestor import IngestAndRetrieveConfig, IngestAndRetrieveResult


def test_config_defaults() -> None:
    print("[TEST] Validating IngestAndRetrieveConfig default values from spec")
    cfg = IngestAndRetrieveConfig()
    assert cfg.batch_size == 128
    assert cfg.max_workers == 4
    assert cfg.embed_model == "deterministic-hash"
    assert cfg.enrichment_model == "qwen2.5-coder:3b"
    assert cfg.tau == 0.01
    assert cfg.weight == 1.5
    assert cfg.output_path is None


def test_config_override() -> None:
    print("[TEST] Validating explicit config overrides replace defaults")
    out = Path("/tmp/sira-artifacts")
    cfg = IngestAndRetrieveConfig(batch_size=64, output_path=out, top_k=10)
    assert cfg.batch_size == 64
    assert cfg.output_path == out
    assert cfg.top_k == 10


def test_result_defaults() -> None:
    print("[TEST] Validating IngestAndRetrieveResult initializes safe empty containers")
    res = IngestAndRetrieveResult()
    assert res.ticket_result is None
    assert res.kb_summary == {}
    assert res.combined_metrics == {}
    assert res.artifacts == {}
