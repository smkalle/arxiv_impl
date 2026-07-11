"""Adapter base helpers."""

from __future__ import annotations

from typing import Any

from metaorch.errors import ContractError


def _require_keys(d: dict[str, Any], keys: tuple[str, ...], where: str) -> None:
    for k in keys:
        if k not in d:
            raise ContractError(f"{where}: missing required key '{k}'")


def _require_type(d: dict[str, Any], key: str, types: tuple[type, ...], where: str) -> None:
    if key in d and not isinstance(d[key], types):
        raise ContractError(
            f"{where}: key '{key}' must be {types}, got {type(d[key]).__name__}"
        )


def _require_int(d: dict[str, Any], key: str, where: str, *, min_value: int | None = None) -> None:
    if key not in d:
        raise ContractError(f"{where}: missing required key '{key}'")
    if not isinstance(d[key], int) or isinstance(d[key], bool):
        raise ContractError(f"{where}: key '{key}' must be int, got {type(d[key]).__name__}")
    if min_value is not None and d[key] < min_value:
        raise ContractError(f"{where}: key '{key}' must be >= {min_value}, got {d[key]}")


def _require_float(d: dict[str, Any], key: str, where: str, *, min_value: float | None = None) -> None:
    if key not in d:
        raise ContractError(f"{where}: missing required key '{key}'")
    if not isinstance(d[key], (int, float)) or isinstance(d[key], bool):
        raise ContractError(f"{where}: key '{key}' must be float, got {type(d[key]).__name__}")
    if min_value is not None and float(d[key]) < min_value:
        raise ContractError(f"{where}: key '{key}' must be >= {min_value}, got {d[key]}")


def _require_str(d: dict[str, Any], key: str, where: str, *, allowed: tuple[str, ...] | None = None) -> None:
    if key not in d:
        raise ContractError(f"{where}: missing required key '{key}'")
    if not isinstance(d[key], str):
        raise ContractError(f"{where}: key '{key}' must be str, got {type(d[key]).__name__}")
    if allowed is not None and d[key] not in allowed:
        raise ContractError(f"{where}: key '{key}' must be one of {allowed}, got '{d[key]}'")


def _require_list(d: dict[str, Any], key: str, where: str) -> None:
    if key not in d:
        raise ContractError(f"{where}: missing required key '{key}'")
    if not isinstance(d[key], list):
        raise ContractError(f"{where}: key '{key}' must be list, got {type(d[key]).__name__}")