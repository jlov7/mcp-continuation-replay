"""Additive TypeScript v2 bridge cut-point checks over the shared SQLite store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from reference.backend import IssueStore, OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.wire_recovery import observation_from_wire
from tests.test_guarded_wire_matrix import BACKEND, _commit, _round_one, _structured
from tests.wire_client import WireError
from typescript_v2_tests.test_typescript_guarded_matrix import _spawn


@pytest.mark.parametrize(
    ("fault", "exit_code"),
    [("exit-after-ledger-insert", 71), ("exit-after-issue-insert", 72)],
)
def test_bridge_precommit_exit_has_no_durable_effect(
    tmp_path: Path, fault: str, exit_code: int
) -> None:
    case = tmp_path / fault
    case.mkdir()
    db = case / "store.sqlite3"
    identity = OperationIdentity(f"ts-{fault}", "alice", BACKEND)
    args = {"operation_id": identity.operation_id, "title": "ts-fault", "mode": "atomic"}
    wire = _spawn(case, db, "server", fault=fault)
    try:
        token = _round_one(wire, args)
        with pytest.raises(WireError, match=f"bridge machinery failure: {exit_code}"):
            _commit(wire, args, token, req_id=11)
        status = _structured(
            wire.request(
                "tools/call",
                {
                    "name": "get_operation_status",
                    "arguments": {"operation_id": identity.operation_id},
                },
                12,
            )
        )
        observation = observation_from_wire(status, expected_identity=identity)
        assert observation.state == "unknown"
        assert (
            ContinuationConsumer(identity).reconcile(lambda _identity: observation).action == "stop"
        )
    finally:
        wire.close()
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == store.operation_count() == 0
    finally:
        store.close()
    frames = [
        json.loads(line[2:])
        for line in (case / "server.transcript.log").read_text(encoding="utf-8").splitlines()
        if line.startswith(("> ", "< "))
    ]
    assert any(frame.get("result", {}).get("resultType") == "input_required" for frame in frames)
    assert any(
        frame.get("id") == 11
        and "error" in frame
        or frame.get("id") == 11
        and frame.get("result", {}).get("isError") is True
        for frame in frames
    )
