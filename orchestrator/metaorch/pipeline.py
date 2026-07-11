"""Canonical run plan + default PipelineContext builders."""

from __future__ import annotations

from metaorch.contract import CANONICAL_FULL_RUN
from metaorch.models import PipelineContext, RunPlan


def canonical_full_run_plan() -> RunPlan:
    return RunPlan(stages=list(CANONICAL_FULL_RUN))


def default_context() -> PipelineContext:
    """A self-contained default context so a vanilla POST /runs works end-to-end with no payload."""
    return PipelineContext(
        ticket_text="how do I reset my MFA on the mobile app?",
        kb_articles=[
            {
                "article_id": "kb-mfa-reset",
                "title": "Resetting multi-factor authentication",
                "body": "To reset MFA: open settings, tap Security, choose Reset MFA, verify via SMS, "
                "then re-enroll a new authenticator device. Common pitfalls: timezone drift, "
                "expired backup codes, and biometric fallback disabled in policy.",
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
            {
                "article_id": "kb-sms-codes",
                "title": "SMS verification codes",
                "body": "SMS verification codes expire after 5 minutes. If a code is rejected, "
                "request a new one. Codes are rate-limited to three per hour per account.",
                "product_area": "notifications",
                "last_updated": "2026-02-20T00:00:00Z",
            },
        ],
        sku_ids=["RAK-TEST-001", "RAK-TEST-002"],
        sources=["gs1", "open_food_facts"],
        acl_groups=["eng-all"],
        extras={
            "source_path": "fixtures/zendesk_1k.csv",
            "source_type": "zendesk",
            "session_id": "demo-session",
        },
    )