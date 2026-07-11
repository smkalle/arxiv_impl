"""Shared pytest fixtures."""

from __future__ import annotations

from typing import Any

import pytest

from metaorch.adapters import default_adapters
from metaorch.contract import Adapter
from metaorch.models import PipelineContext, StageKind


@pytest.fixture
def adapters() -> dict[StageKind, Adapter]:
    return default_adapters()


@pytest.fixture
def sample_kb() -> list[dict[str, Any]]:
    return [
        {
            "article_id": "kb-mfa-reset",
            "title": "Resetting multi-factor authentication",
            "body": "To reset MFA: open settings, tap Security, choose Reset MFA, verify via SMS, "
                    "then re-enroll a new authenticator device.",
            "product_area": "identity",
            "last_updated": "2026-04-01T00:00:00Z",
        },
        {
            "article_id": "kb-mobile-auth",
            "title": "Mobile authenticator enrollment",
            "body": "Enroll a new mobile authenticator device under Security > Devices > Add. "
                    "Supported: iOS Authenticator, Android Authenticator, hardware TOTP tokens.",
            "product_area": "identity",
            "last_updated": "2026-03-15T00:00:00Z",
        },
    ]


@pytest.fixture
def enriched_corpus(sample_kb: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "article_id": a["article_id"],
            "title": a["title"],
            "enriched_body": a["body"] + " [enriched]",
            "enriched_terms": sorted(
                {w for w in (*a["title"].split(), a["product_area"]) if len(w) > 4}
            ),
        }
        for a in sample_kb
    ]


@pytest.fixture
def default_context(sample_kb: list[dict[str, Any]]) -> PipelineContext:
    return PipelineContext(
        ticket_text="how do I reset my MFA on the mobile app?",
        kb_articles=sample_kb,
        sku_ids=["RAK-TEST-001", "RAK-TEST-002"],
        sources=["gs1"],
        acl_groups=["eng-all"],
        extras={"source_path": "fixtures/zendesk_1k.csv", "source_type": "zendesk"},
    )