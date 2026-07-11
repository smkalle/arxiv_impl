"""Config shim. The actual Settings + load_settings live in metaorch.contract."""

from __future__ import annotations

from metaorch.contract import Settings, load_settings

__all__ = ["Settings", "load_settings"]