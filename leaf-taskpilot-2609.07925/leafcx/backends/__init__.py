"""Backend selection.

`ollama` is the default and mirrors the reference tutorial. `openai` covers
llama.cpp's `llama-server` and any other OpenAI-compatible endpoint, which is
the Termux-friendly path. `gold` and `noop` need no model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config import AgentConfig
from .base import AssistantMessage, Backend, BackendError, ToolCall, coerce_arguments
from .http import OllamaBackend, OpenAICompatibleBackend
from .offline import GoldBackend, NoopBackend, ScriptedBackend

BACKEND_NAMES = ("ollama", "openai", "gold", "noop")


def make_backend(
    config: AgentConfig | None = None,
    task: Any = None,
    workspace: Path | None = None,
) -> Backend:
    """Build the backend named by `config.backend`."""
    config = config or AgentConfig()
    name = (config.backend or "ollama").lower()
    if name == "ollama":
        return OllamaBackend(config)
    if name in {"openai", "llamacpp", "llama.cpp", "openai-compatible"}:
        return OpenAICompatibleBackend(config)
    if name == "noop":
        return NoopBackend()
    if name == "gold":
        if task is None or workspace is None:
            raise ValueError("the gold backend needs a task and a materialised workspace")
        return GoldBackend(task, workspace)
    raise ValueError(f"unknown backend {config.backend!r}; known: {', '.join(BACKEND_NAMES)}")


__all__ = [
    "BACKEND_NAMES",
    "AssistantMessage",
    "Backend",
    "BackendError",
    "GoldBackend",
    "NoopBackend",
    "OllamaBackend",
    "OpenAICompatibleBackend",
    "ScriptedBackend",
    "ToolCall",
    "coerce_arguments",
    "make_backend",
]
