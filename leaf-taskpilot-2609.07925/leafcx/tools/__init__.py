"""Tool registry: Leaf's five file tools plus three domain tools.

`ask_customer` is registered only when the simulated-customer flag is on, so a
single-shot episode never sees a tool it is not supposed to use.
"""

from __future__ import annotations

from typing import Any, Callable

from .domain import DOMAIN_TOOL_SCHEMAS, DOMAIN_TOOLS
from .files import FILE_TOOL_SCHEMAS, FILE_TOOLS

#: Names in the order the paper lists them, then ours.
LEAF_TOOL_NAMES = ("read", "write", "edit", "glob", "bash")
DOMAIN_TOOL_NAMES = ("search_inventory", "quote_finance", "validate_account")

TOOLS: dict[str, Callable[..., str]] = {**FILE_TOOLS, **DOMAIN_TOOLS}
TOOL_SCHEMAS: list[dict[str, Any]] = [*FILE_TOOL_SCHEMAS, *DOMAIN_TOOL_SCHEMAS]

ASK_CUSTOMER_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "ask_customer",
        "description": (
            "Ask the customer one short clarifying question. Only available when the "
            "request is ambiguous. Ask about one thing at a time."
        ),
        "parameters": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
        },
    },
}


def build_toolset(user_sim: Callable[[str], str] | None = None):
    """Return `(callables, schemas)` for one episode."""
    callables = dict(TOOLS)
    schemas = [dict(schema) for schema in TOOL_SCHEMAS]
    if user_sim is not None:
        callables["ask_customer"] = lambda question: user_sim(question)
        schemas.append(dict(ASK_CUSTOMER_SCHEMA))
    return callables, schemas


__all__ = [
    "ASK_CUSTOMER_SCHEMA",
    "DOMAIN_TOOL_NAMES",
    "LEAF_TOOL_NAMES",
    "TOOLS",
    "TOOL_SCHEMAS",
    "build_toolset",
]
