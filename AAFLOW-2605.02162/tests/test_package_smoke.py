from click.testing import CliRunner

from kb_ingestor import IngestConfig, IngestResult, ingest
from kb_ingestor.cli import cli
from kb_ingestor.ops import chunk, embed, load, upsert


def test_public_exports_importable() -> None:
    assert ingest is not None
    assert IngestConfig is not None
    assert IngestResult is not None
    assert load is not None
    assert chunk is not None
    assert embed is not None
    assert upsert is not None


def test_cli_help_smoke() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "benchmark" in result.output
    assert "validate" in result.output
