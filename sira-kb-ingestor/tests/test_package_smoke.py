from click.testing import CliRunner

from sira_kb_ingestor import (
    ArtifactBuildError,
    EmbedDimMismatchError,
    EmbedModelError,
    EnrichmentError,
    IngestAndRetrieveConfig,
    IngestAndRetrieveResult,
    IngestNullError,
    IngestSchemaError,
    RetrievalError,
)
from sira_kb_ingestor.cli import cli


def test_import_smoke() -> None:
    print("[TEST] Validating public API exports and typed error constructors")
    assert IngestAndRetrieveConfig is not None
    assert IngestAndRetrieveResult is not None
    assert IngestSchemaError("x")
    assert IngestNullError("x")
    assert EmbedModelError("x")
    assert EmbedDimMismatchError("x")
    assert ArtifactBuildError("x")
    assert EnrichmentError("x")
    assert RetrievalError("x")


def test_cli_help_smoke() -> None:
    print("[TEST] Validating CLI help exposes all planned subcommands")
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "setup" in result.output
    assert "query" in result.output
    assert "server" in result.output
    assert "benchmark" in result.output
