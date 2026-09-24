"""Wire-level reproduction of the two central findings (Milestone B).

Milestone A established the findings over the SDK's in-process transport, which
cannot prove a guarantee survives transport. These tests repeat both against a
REAL stdio subprocess using raw newline-delimited JSON-RPC, with every byte
recorded to a transcript.

Pinned witness tests assert the exact observed unmediated behavior and pass only
while that mechanism remains unchanged. The read-back oracle is the SQLite
store, never the agent's success text.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from reference.backend import IssueStore
from reference.readback import ReadBack
from tests.wire_client import RawStdioClient

TITLE = "wire-spec"


@pytest.fixture
def oracle(wire_client: RawStdioClient) -> Iterator[tuple[IssueStore, ReadBack]]:
    """Read-back over the server's OWN per-test DB, keeping the server alive.

    The store must remain open for the whole test because read-back reads the
    same file the server writes; closing/reopening would interleave with the
    server's own connection.
    """
    store = IssueStore(str(wire_client.db_path), backend_id="sqlite:wire-test")
    yield store, ReadBack(store, principal="stdio:anonymous")
    store.close()


def _call(wire: RawStdioClient, params: dict, req_id: int) -> dict:
    return wire.request("tools/call", params, req_id)


def _round_one(wire: RawStdioClient, req_id: int = 10) -> str:
    result = _call(wire, {"name": "create_issue", "arguments": {"title": TITLE}}, req_id)
    assert result.get("resultType") == "input_required", f"expected MRTR on the wire, got {result}"
    token = result.get("requestState")
    assert token, "no requestState on the wire"
    return str(token)


def _retry(wire: RawStdioClient, token: str, body: str, req_id: int):
    return _call(
        wire,
        {
            "name": "create_issue",
            "arguments": {"title": TITLE},
            "inputResponses": {"body": {"action": "accept", "content": {"body": body}}},
            "requestState": token,
        },
        req_id,
    )


def test_wire_legitimate_round_trip_completes_once(
    wire_client: RawStdioClient, oracle: tuple[IssueStore, ReadBack]
) -> None:
    """Control: the legitimate single-round exchange works over the raw wire."""
    store, rb = oracle
    token = _round_one(wire_client)
    result = _retry(wire_client, token, "alpha", 11)
    assert result.get("isError", False) is False
    assert store.count() == 1
    assert rb.observe_by_title(TITLE, operation_id="wire-control").effects == 1


@pytest.mark.pinned_finding(mechanism="duplicate_effect")
def test_wire_identical_retry_does_not_duplicate_the_effect(
    wire_client: RawStdioClient, oracle: tuple[IssueStore, ReadBack]
) -> None:
    """Pinned H2 witness: identical wire replay creates two effects."""
    _, rb = oracle
    token = _round_one(wire_client, 20)
    _retry(wire_client, token, "alpha", 21)
    _retry(wire_client, token, "alpha", 22)
    observed = rb.observe_by_title(TITLE, operation_id="wire-h2")
    assert observed.effects == 2 and observed.matching_ids == (1, 2)


@pytest.mark.pinned_finding(mechanism="changed_input_dispatched")
def test_wire_changed_input_responses_conflicts_before_dispatch(
    wire_client: RawStdioClient, oracle: tuple[IssueStore, ReadBack]
) -> None:
    """Pinned H1 witness: changed inputResponses dispatches on the wire."""
    _, rb = oracle
    token = _round_one(wire_client, 30)
    _retry(wire_client, token, "alpha", 31)
    result = _retry(wire_client, token, "beta", 32)
    assert result.get("isError", False) is False
    assert rb.observe_by_body("beta", operation_id="wire-h1").effects == 1


def test_wire_transcript_was_captured(
    wire_client: RawStdioClient, oracle: tuple[IssueStore, ReadBack]
) -> None:
    """The transcript file contains MRTR-bearing bytes that actually reached the wire."""
    token = _round_one(wire_client, 40)
    _retry(wire_client, token, "alpha", 41)
    transcript = wire_client._t.name
    outbound = [
        json.loads(line[2:])
        for line in Path(transcript).read_text().splitlines()
        if line.startswith("> ")
    ]
    continuation = next(
        frame
        for frame in outbound
        if frame.get("method") == "tools/call" and "requestState" in frame.get("params", {})
    )
    params = continuation["params"]
    assert params["requestState"] == token
    assert params["inputResponses"]["body"]["content"]["body"] == "alpha"
    assert params["_meta"]["io.modelcontextprotocol/protocolVersion"] == "2026-07-28"
