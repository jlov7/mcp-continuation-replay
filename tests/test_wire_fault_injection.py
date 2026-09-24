"""Case 09 at WIRE level — crash AFTER backend commit, BEFORE local receipt.

Earlier evidence only *modelled* the lost reply by having the client retry.
This test injects the fault: the server commits the effect to SQLite, then
hard-exits (`os._exit`) before writing the response. The client sees a closed
connection with no reply — a real crash between commit and receipt.

Two assertions, kept apart so a passing property is never dragged down by a
finding:

1. `test_case_09a...` — the consumer's outcome after a dropped reply is
   `unknown`, never `not_applied`. A title diagnostic sees the row but is
   correctly refused as authoritative reconciliation.
2. `test_case_09b...` — replaying the same logical continuation after the
   crash must NOT create a second record. (Safe property — FAILS, preserved
   as a finding: the pinned SDK keeps no consumed-token record, so the replay
   re-dispatches. Same root cause as cases 01/03.)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from reference.backend import IssueStore, OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.readback import ReadBack
from tests.wire_client import RawStdioClient, WireError

ROOT = Path(__file__).resolve().parents[1]
TITLE = "wire-crash-09"


def _spawn(db_path: Path, transcript_path: Path, fault: bool) -> RawStdioClient:
    return RawStdioClient(
        server_cmd=[sys.executable, str(ROOT / "reference" / "server_stdio.py")],
        transcript_path=transcript_path,
        db_path=db_path,
        extra_env={"WIRE_FAULT": "drop-after-commit"} if fault else None,
    )


def _round_one(wire: RawStdioClient, req_id: int = 10) -> str:
    result = wire.request(
        "tools/call", {"name": "create_issue", "arguments": {"title": TITLE}}, req_id
    )
    assert result.get("resultType") == "input_required"
    token = result.get("requestState")
    assert token, "no requestState on the wire"
    return str(token)


def _commit(wire: RawStdioClient, token: str, body: str, req_id: int) -> dict:
    return wire.request(
        "tools/call",
        {
            "name": "create_issue",
            "arguments": {"title": TITLE},
            "inputResponses": {"body": {"action": "accept", "content": {"body": body}}},
            "requestState": token,
        },
        req_id,
    )


def test_case_09a_wire_crash_outcome_is_unknown_never_not_applied(
    tmp_path: Path,
) -> None:
    """The consumer reports `unknown` after an injected crash.

    A transport failure before any reply is never read as `not_applied`.
    A diagnostic read reveals the effect landed, but it cannot settle the
    identity-bound consumer because the wire fixture has no operation ledger.
    """
    db = tmp_path / "crash.db"
    identity = OperationIdentity("case-09a", "stdio:anonymous", "sqlite:wire-test")
    consumer = ContinuationConsumer(identity)
    wire = _spawn(db, tmp_path / "crash-a.transcript.log", fault=True)
    try:
        wire.open_connection()
        token = _round_one(wire)
        with pytest.raises(WireError) as caught:
            _commit(wire, token, "alpha", 11)
        uncertain = consumer.transport_failed(caught.value)
        assert uncertain.submission == "unknown"
        assert uncertain.effect == "unknown"
        assert uncertain.observation is None
    finally:
        wire.close()

    store = IssueStore(str(db), backend_id="sqlite:wire-test")
    try:
        rb = ReadBack(store, principal="stdio:anonymous")
        observed = rb.observe_by_title(TITLE, operation_id=identity.operation_id)
        assert observed.state == "applied", (
            f"effect landed despite the crash; observation was {observed.state}"
        )
        assert observed.effects == 1
        assert observed.authoritative is False
        with pytest.raises(ValueError, match="diagnostic observations cannot settle"):
            consumer.reconcile(lambda _identity: observed)
    finally:
        store.close()


@pytest.mark.pinned_finding(mechanism="duplicate_effect_after_crash")
def test_case_09b_wire_crash_replay_does_not_create_second_record(
    tmp_path: Path,
) -> None:
    """SAFE: replaying the same logical continuation after a crash is ONE effect.

    The crash leaves the client `unknown`. Correct recovery is reconcile-then-
    reply, not blind replay. A blind replay must not create a second record.
    On the pinned SDK this FAILS — a finding preserved.
    """
    db = tmp_path / "crash-b.db"
    wire = _spawn(db, tmp_path / "crash-b.transcript.log", fault=True)
    try:
        wire.open_connection()
        token = _round_one(wire)
        with pytest.raises(WireError):
            _commit(wire, token, "alpha", 11)
    finally:
        wire.close()

    live = _spawn(db, tmp_path / "crash-b-replay.transcript.log", fault=False)
    store = IssueStore(str(db), backend_id="sqlite:wire-test")
    try:
        rb = ReadBack(store, principal="stdio:anonymous")
        live.open_connection()
        live_result = _commit(live, token, "alpha", 12)
        assert live_result.get("isError", False) is False
        observed = rb.observe_by_title(TITLE, operation_id="case-09b")
        assert observed.effects == 2 and observed.matching_ids == (1, 2)
    finally:
        live.close()
        store.close()
