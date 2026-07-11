"""Adapter registry. Importing this package registers all eight adapters."""

from __future__ import annotations

from metaorch.adapters.aaflow_adapter import AaflowAdapter
from metaorch.adapters.datamaster_adapter import DataMasterAdapter
from metaorch.adapters.evolvemem_adapter import EvolvememAdapter
from metaorch.adapters.jina_adapter import JinaAdapter
from metaorch.adapters.rgqm_adapter import RgqmAdapter
from metaorch.adapters.sira_adapter import SiraAdapter
from metaorch.adapters.sira_ingestor_adapter import SiraIngestorAdapter
from metaorch.adapters.tkmem_adapter import TkmemAdapter
from metaorch.contract import Adapter
from metaorch.models import StageKind


def default_adapters() -> dict[StageKind, Adapter]:
    """Return a fresh dict mapping every StageKind to its default adapter instance."""
    instances = [
        AaflowAdapter(),
        SiraIngestorAdapter(),
        JinaAdapter(),
        SiraAdapter(),
        TkmemAdapter(),
        DataMasterAdapter(),
        EvolvememAdapter(),
        RgqmAdapter(),
    ]
    return {a.kind: a for a in instances}


__all__ = [
    "AaflowAdapter",
    "SiraIngestorAdapter",
    "JinaAdapter",
    "SiraAdapter",
    "TkmemAdapter",
    "DataMasterAdapter",
    "EvolvememAdapter",
    "RgqmAdapter",
    "default_adapters",
]