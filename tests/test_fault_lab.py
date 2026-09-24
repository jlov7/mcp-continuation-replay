"""Additive fault lab; frozen twelve-case matrix remains unchanged."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from reference.backend import IssueStore, OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.readback import ReadBack
from tests.test_guarded_wire_matrix import BACKEND, _args, _commit, _round_one, _spawn
from tests.wire_client import WireError


@pytest.mark.parametrize(
    ("fault", "exit_code"),
    [("exit-after-ledger-insert", 71), ("exit-after-issue-insert", 72)],
)
def test_precommit_hard_exit_rolls_back_both_rows(
    tmp_path: Path, fault: str, exit_code: int
) -> None:
    case = tmp_path / fault
    case.mkdir()
    db = case / "store.sqlite3"
    operation_id = f"lab-{fault}"
    args = {**_args("lab"), "operation_id": operation_id}
    wire = _spawn(case, db, "crash", fault=fault)
    token = _round_one(wire, args)
    consumer = ContinuationConsumer(OperationIdentity(operation_id, "alice", BACKEND))
    with pytest.raises(WireError) as caught:
        _commit(wire, args, token, req_id=11)
    assert consumer.transport_failed(caught.value).effect == "unknown"
    assert wire.returncode == exit_code
    wire.close()

    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == store.operation_count() == 0
        observation = ReadBack(store, principal="alice").reconcile_operation(consumer.identity)
        assert observation.state == "unknown" and observation.authoritative
        assert consumer.reconcile(lambda _identity: observation).action == "stop"
    finally:
        store.close()

    transcript = (case / "crash.transcript.log").read_text(encoding="utf-8")
    frames = [
        json.loads(line[2:]) for line in transcript.splitlines() if line.startswith(("> ", "< "))
    ]
    assert any(frame.get("result", {}).get("resultType") == "input_required" for frame in frames)
    assert any(frame.get("method") == "tools/call" and frame.get("id") == 11 for frame in frames)
    assert not any(frame.get("id") == 11 and "result" in frame for frame in frames)


def test_sqlite_busy_fails_before_dispatch_and_preserves_identity(tmp_path: Path) -> None:
    db = tmp_path / "busy.sqlite3"
    first = IssueStore(str(db), backend_id=BACKEND)
    second = IssueStore(str(db), backend_id=BACKEND)
    identity = OperationIdentity("lab-busy", "alice", BACKEND)
    try:
        second._conn.execute("PRAGMA busy_timeout = 0")
        first._conn.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            second.apply_issue_once(identity, request_fingerprint="same", title="busy", body="body")
        first._conn.rollback()
        assert first.count() == first.operation_count() == 0
        applied = second.apply_issue_once(
            identity, request_fingerprint="same", title="busy", body="body"
        )
        replay = first.apply_issue_once(
            identity, request_fingerprint="same", title="busy", body="body"
        )
        assert applied.replayed is False and replay.replayed is True
        assert first.count() == first.operation_count() == 1
    finally:
        first.close()
        second.close()


def test_exception_after_issue_insert_rolls_back_both_rows(tmp_path: Path) -> None:
    db = tmp_path / "rollback.sqlite3"
    store = IssueStore(str(db), backend_id=BACKEND)
    identity = OperationIdentity("lab-rollback", "alice", BACKEND)

    def fail(point: str) -> None:
        if point == "after-issue-insert":
            raise RuntimeError("injected before commit")

    try:
        with pytest.raises(RuntimeError, match="injected before commit"):
            store.apply_issue_once(
                identity, request_fingerprint="same", title="rollback", body="body", fault_hook=fail
            )
        assert store.count() == store.operation_count() == 0
        result = store.apply_issue_once(
            identity, request_fingerprint="same", title="rollback", body="body"
        )
        assert not result.replayed
        assert store.count() == store.operation_count() == 1
    finally:
        store.close()
