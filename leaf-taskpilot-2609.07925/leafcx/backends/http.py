"""Ollama and OpenAI-compatible backends over stdlib HTTP.

Ollama first, because that is what the tutorial this port follows uses and what
most people already have running.  The OpenAI-compatible backend covers
llama.cpp's `llama-server`, which is the practical way to run a 4B model on a
phone (Termux has no supported Ollama build), and any remote endpoint.

No third-party HTTP dependency: `urllib` is enough and keeps `pip install` on a
phone down to pytest.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from ..config import AgentConfig
from .base import AssistantMessage, BackendError, ToolCall, coerce_arguments

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OPENAI_URL = "http://127.0.0.1:8080/v1"


def _post(url: str, payload: dict[str, Any], timeout: int, headers: dict[str, str] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method="POST")
    request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise BackendError(f"{url} returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise BackendError(f"cannot reach {url}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise BackendError(f"{url} timed out after {timeout}s") from exc


def _strip_thinking(content: str) -> str:
    """Drop a `<think>` block if the server left one in the content field."""
    if "<think>" in content and "</think>" in content:
        head, _, tail = content.partition("</think>")
        if "<think>" in head:
            return tail.strip()
    return content


class OllamaBackend:
    """Talks to a local Ollama daemon's native `/api/chat` tool-calling endpoint."""

    name = "ollama"

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        self.base_url = (self.config.base_url or DEFAULT_OLLAMA_URL).rstrip("/")

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "tools": tools,
            "stream": False,
            "options": {
                "temperature": self.config.temperature,
                "top_p": self.config.top_p,
                "num_ctx": self.config.num_ctx,
                "num_predict": self.config.num_predict,
            },
        }
        data = _post(f"{self.base_url}/api/chat", payload, self.config.request_timeout)
        message = data.get("message") or {}
        calls = [
            ToolCall(
                name=(call.get("function") or {}).get("name", ""),
                arguments=coerce_arguments((call.get("function") or {}).get("arguments")),
                call_id=str(call.get("id") or ""),
            )
            for call in (message.get("tool_calls") or [])
        ]
        return AssistantMessage(
            content=_strip_thinking(message.get("content") or ""),
            tool_calls=[c for c in calls if c.name],
            raw=message,
        )


class OpenAICompatibleBackend:
    """Talks to any `/v1/chat/completions` server: llama.cpp, vLLM, a remote API.

    For llama.cpp, start the server with `--jinja` so the model's own chat
    template drives tool calling.
    """

    name = "openai"

    def __init__(self, config: AgentConfig | None = None) -> None:
        self.config = config or AgentConfig()
        base = (self.config.base_url or DEFAULT_OPENAI_URL).rstrip("/")
        self.base_url = base if base.endswith("/v1") else f"{base}/v1"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        payload = {
            "model": self.config.model,
            "messages": [_to_openai(m) for m in messages],
            "tools": tools,
            "tool_choice": "auto",
            "temperature": self.config.temperature,
            "top_p": self.config.top_p,
            "max_tokens": self.config.num_predict,
            "stream": False,
        }
        data = _post(
            f"{self.base_url}/chat/completions",
            payload,
            self.config.request_timeout,
            headers={"Authorization": f"Bearer {self.config.api_key}"},
        )
        choices = data.get("choices") or []
        if not choices:
            raise BackendError(f"no choices in response: {json.dumps(data)[:300]}")
        message = choices[0].get("message") or {}
        calls = [
            ToolCall(
                name=(call.get("function") or {}).get("name", ""),
                arguments=coerce_arguments((call.get("function") or {}).get("arguments")),
                call_id=str(call.get("id") or ""),
            )
            for call in (message.get("tool_calls") or [])
        ]
        return AssistantMessage(
            content=_strip_thinking(message.get("content") or ""),
            tool_calls=[c for c in calls if c.name],
            raw=message,
        )


def _to_openai(message: dict[str, Any]) -> dict[str, Any]:
    """Translate the loop's internal message shape to OpenAI's wire format.

    The loop stores tool results the way Ollama wants them (`tool_name`);
    OpenAI-compatible servers want `tool_call_id`.
    """
    if message.get("role") != "tool":
        return message
    converted = {"role": "tool", "content": message.get("content", "")}
    if message.get("tool_call_id"):
        converted["tool_call_id"] = message["tool_call_id"]
    if message.get("tool_name"):
        converted["name"] = message["tool_name"]
    return converted
