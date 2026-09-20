"""Backend protocol and the normalised message shape the agent loop speaks."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    call_id: str = ""


@dataclass
class AssistantMessage:
    """One assistant turn.

    An empty `tool_calls` list is the termination signal: the paper ends the
    episode when the model replies without calling a tool.
    """

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def is_final(self) -> bool:
        return not self.tool_calls


class Backend(Protocol):
    name: str

    def chat(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> AssistantMessage: ...


def coerce_arguments(raw: Any) -> dict[str, Any]:
    """Tool arguments arrive as a dict or as a JSON string, depending on server."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {"_unparsed": raw}
        return parsed if isinstance(parsed, dict) else {"_unparsed": raw}
    return {}


class BackendError(RuntimeError):
    """Raised when the model server is unreachable or answers with an error."""
