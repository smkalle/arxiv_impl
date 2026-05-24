"""
LLM provider abstraction for diagnosis modules.
Selects Anthropic or Ollama based on DIAGNOSIS_LLM_PROVIDER env var.
"""
from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, system: str, user: str, temperature: float = 0.3) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str = "claude-haiku-4-5-20251001", api_key: str = "") -> None:
        try:
            import anthropic as _anthropic
            self._client = _anthropic.Anthropic(api_key=api_key or None)
        except ImportError as e:
            raise ImportError("anthropic package not installed. Run: pip install anthropic") from e
        self._model = model

    def complete(self, system: str, user: str, temperature: float = 0.3) -> str:
        msg = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text


class OllamaProvider:
    def __init__(self, model: str = "llama3", host: str = "http://localhost:11434") -> None:
        self._model = model
        self._host = host.rstrip("/")

    def complete(self, system: str, user: str, temperature: float = 0.3) -> str:
        try:
            import httpx
        except ImportError as e:
            raise ImportError("httpx package not installed. Run: pip install httpx") from e
        payload = {
            "model": self._model,
            "prompt": f"{system}\n\n{user}",
            "stream": False,
            "options": {"temperature": temperature},
        }
        r = httpx.post(f"{self._host}/api/generate", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["response"]


class MockProvider:
    """Deterministic mock for tests — returns configurable JSON."""

    def __init__(self, response: str = '{"top_k": 7, "bm25_weight": 1.2}') -> None:
        self._response = response

    def complete(self, system: str, user: str, temperature: float = 0.3) -> str:
        return self._response


def get_provider(provider: str = "anthropic", **kwargs) -> LLMProvider:
    if provider == "ollama":
        return OllamaProvider(
            model=kwargs.get("model", "llama3"),
            host=kwargs.get("host", "http://localhost:11434"),
        )
    if provider == "mock":
        return MockProvider(response=kwargs.get("response", '{"top_k": 7}'))
    return AnthropicProvider(
        model=kwargs.get("model", "claude-haiku-4-5-20251001"),
        api_key=kwargs.get("api_key", ""),
    )


def extract_json(text: str) -> dict:
    """Extract the first JSON object from an LLM response string."""
    # Try the whole string first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Find first {...} block
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}
