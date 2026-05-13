from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any
import uuid


def _short_uuid() -> str:
    return str(uuid.uuid4())[:8]


class ManifestMeta(BaseModel):
    manifest_id: str = Field(default_factory=_short_uuid)
    source: str                         # "gs1" | "open_food_facts" | "schema_org"
    source_url: str
    sku_id: str
    gtin: str | None = None
    schema_fingerprint: str             # sha256 of aligned column names
    coverage: dict[str, bool] = Field(default_factory=dict)
    score_delta: float | None = None
    committed: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provenance: str                     # "red_node_{node_id}"


class Manifest(BaseModel):
    meta: ManifestMeta
    data: dict[str, Any] = Field(default_factory=dict)
