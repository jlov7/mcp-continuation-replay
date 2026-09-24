"""The operation fingerprint — the cross-language equivalence contract.

Protocol §1 binds an operation by five components:

    principal  ⊗  tool_id/version  ⊗  canonical(arguments)
               ⊗  continuation_state
               ⊗  input_responses

This module defines the EXACT canonicalization both adapters must share, so a
logical request has ONE fingerprint no matter which language computes it.

Canonicalization (declared, and the same in `adapters/typescript/`):
- JSON objects use Unicode scalar-value key order, compact separators, UTF-8;
- numbers must be integral and within JavaScript's safe range;
- opaque/stateful fields (`continuation_state`, `input_responses`) are bound
  through HMAC-SHA256 with a caller-supplied deployment key;
- the SHA-256 of the canonical payload is the fingerprint digest.

The key is required: this package has no public fallback that could be mistaken
for confidentiality. Digests still leak equality. See research/PROTOCOL.md.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["LogicalRequest", "fingerprint"]

_OPAQUE_FIELDS = ("continuation_state", "input_responses")


@dataclass(frozen=True, slots=True)
class LogicalRequest:
    """The logical operation a fingerprint binds — not a network attempt."""

    principal: str | None
    tool_id: str
    tool_version: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    continuation_state: str | None = None
    input_responses: Mapping[str, Any] | None = None


def _validate_string(value: str, *, path: str) -> None:
    if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raise ValueError(f"{path}: unpaired UTF-16 surrogate is not valid Unicode")


def _canonical_text(value: Any, *, path: str = "$") -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        _validate_string(value, path=path)
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, int):
        if abs(value) > 2**53 - 1:
            raise ValueError(f"{path}: integer is outside the interoperable safe range")
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer() or abs(value) > 2**53 - 1:
            raise ValueError(f"{path}: number must be an integer in the interoperable safe range")
        return str(int(value))
    if isinstance(value, Mapping):
        items: list[str] = []
        if any(not isinstance(key, str) for key in value):
            raise ValueError(f"{path}: object keys must be strings")
        for key in sorted(value):
            _validate_string(key, path=f"{path}.<key>")
            encoded_key = json.dumps(key, ensure_ascii=False, separators=(",", ":"))
            items.append(f"{encoded_key}:{_canonical_text(value[key], path=f'{path}.{key}')}")
        return "{" + ",".join(items) + "}"
    if isinstance(value, (list, tuple)):
        return (
            "["
            + ",".join(
                _canonical_text(item, path=f"{path}[{index}]") for index, item in enumerate(value)
            )
            + "]"
        )
    raise ValueError(f"{path}: unsupported JSON value {type(value).__name__}")


def _canonical_bytes(value: Any) -> bytes:
    return _canonical_text(value).encode("utf-8")


def _bind_opaque(field_name: str, value: Any, key: bytes) -> str:
    """Keyed digest of an opaque field — leaks equality, not the state bytes."""
    msg = field_name.encode("utf-8") + b"\x00" + _canonical_bytes(value)
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def fingerprint(request: LogicalRequest, *, key: bytes) -> str:
    """Canonical SHA-256 over the five bound components.

    Identical logical requests → identical digest, in both Python and
    TypeScript (the TS adapter implements this exact canonicalization).
    """
    if len(key) < 32:
        raise ValueError("fingerprint key must contain at least 32 bytes")
    payload: dict[str, Any] = {
        "principal": request.principal,
        "tool_id": request.tool_id,
        "tool_version": request.tool_version,
        "arguments": request.arguments,
    }
    for f in _OPAQUE_FIELDS:
        payload[f] = _bind_opaque(f, getattr(request, f), key)
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()
