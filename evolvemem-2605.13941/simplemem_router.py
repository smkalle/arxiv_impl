"""
SimpleMem router — delegates to the real aiming-lab/SimpleMem library
or falls back to the stub based on settings.simplemem_use_stub.

Real SimpleMem setup:
  git clone https://github.com/aiming-lab/SimpleMem.git SimpleMem
  cd SimpleMem && pip install -r requirements.txt

Then set SIMPLEMEM_USE_STUB=false (or simplemem_use_stub=False in settings).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


class SimplememRouter:
    def __init__(self, settings: Any) -> None:
        self._use_stub: bool = getattr(settings, "simplemem_use_stub", True)
        self._lancedb_uri: str = getattr(settings, "lancedb_uri", "data/lancedb")
        self._inner: Any = None

    # ── Public API (mirrors SimpleMem + stub) ────────────────────────────────

    def create(self, mode: str = "text") -> "SimplememRouter":
        if self._use_stub:
            from simplemem_router_stub import StubSimpleMemRouter
            self._inner = StubSimpleMemRouter(
                lancedb_uri=self._lancedb_uri
            ).create(mode)
        else:
            self._inner = self._load_real(mode)
        return self

    def add_dialogue(
        self,
        user: str,
        assistant: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._inner.add_dialogue(user=user, assistant=assistant, metadata=metadata or {})

    def finalize(self) -> None:
        self._inner.finalize()

    def ask(self, query: str, config: Any = None) -> list[dict[str, Any]]:
        return self._inner.ask(query=query, config=config)

    # ── Real SimpleMem loader ────────────────────────────────────────────────

    def _load_real(self, mode: str) -> Any:
        simplemem_path = Path(__file__).parent / "SimpleMem"
        if not simplemem_path.exists():
            raise RuntimeError(
                f"SimpleMem not found at {simplemem_path}. "
                "Clone it: git clone https://github.com/aiming-lab/SimpleMem.git SimpleMem\n"
                "Or set SIMPLEMEM_USE_STUB=true to use the stub."
            )
        if str(simplemem_path) not in sys.path:
            sys.path.insert(0, str(simplemem_path))
        try:
            from simplemem_router import SimpleMemRouter as _Real  # type: ignore
            router = _Real(lancedb_uri=self._lancedb_uri)
            return router.create(mode=mode)
        except ImportError as e:
            import warnings
            warnings.warn(
                f"Failed to import real SimpleMem ({e}). Falling back to stub.",
                RuntimeWarning,
                stacklevel=2,
            )
            from simplemem_router_stub import StubSimpleMemRouter
            return StubSimpleMemRouter(lancedb_uri=self._lancedb_uri).create(mode)
