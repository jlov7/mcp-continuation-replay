"""Installed JSONL bridge for the operation-fingerprint contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from typing import Any

from continuation_replay import __version__
from continuation_replay.fingerprint import LogicalRequest, fingerprint

KEY_ENV = "CONTINUATION_REPLAY_FINGERPRINT_KEY_HEX"


def _key_from_environment() -> bytes:
    value = os.environ.get(KEY_ENV, "")
    try:
        key = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError(f"{KEY_ENV} must be hexadecimal") from exc
    if len(key) < 32:
        raise ValueError(f"{KEY_ENV} must contain at least 32 bytes")
    return key


def _request(value: Any) -> LogicalRequest:
    if not isinstance(value, dict):
        raise TypeError("request must be a JSON object")
    try:
        return LogicalRequest(
            principal=value.get("principal"),
            tool_id=value["tool_id"],
            tool_version=value["tool_version"],
            arguments=value.get("arguments", {}),
            continuation_state=value.get("continuation_state"),
            input_responses=value.get("input_responses"),
        )
    except KeyError as exc:
        raise ValueError(f"request is missing {exc.args[0]!r}") from exc


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="continuation-replay-fingerprint",
        description="Read LogicalRequest JSON objects from stdin and print SHA-256 fingerprints.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args(argv)
    line_number = 0
    try:
        key = _key_from_environment()
        for line_number, raw in enumerate(sys.stdin, start=1):
            if not raw.strip():
                continue
            value = json.loads(raw)
            print(fingerprint(_request(value), key=key))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(
            f"continuation-replay-fingerprint: line {line_number}: {exc}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
