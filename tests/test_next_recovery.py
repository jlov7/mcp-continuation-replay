"""Additive status-only recovery and post-commit partial crash regressions."""

from __future__ import annotations

import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path

import pytest

from reference.backend import IssueStore, OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.readback import EffectObservation
from reference.wire_recovery import observation_from_wire
from tests.test_guarded_wire_matrix import BACKEND, _args, _commit, _round_one, _spawn
from tests.wire_client import WireError


def _status(wire, identity: OperationIdentity, request_id: int) -> dict:
    reply = wire.request(
        "tools/call",
        {"name": "get_operation_status", "arguments": {"operation_id": identity.operation_id}},
        request_id,
    )
    value = reply["structuredContent"]
    assert isinstance(value, dict)
    return value


def test_status_only_recovers_durable_result_without_redispatch(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    args = _args("next-result")
    identity = OperationIdentity(args["operation_id"], "alice", BACKEND)
    crashed = _spawn(tmp_path, db, "crashed", fault="drop-after-commit")
    token = _round_one(crashed, args)
    with pytest.raises(WireError):
        _commit(crashed, args, token, req_id=11)
    assert crashed.returncode == 70
    crashed.close()

    restarted = _spawn(tmp_path, db, "restarted")
    try:
        status = _status(restarted, identity, 12)
        observation = observation_from_wire(status, expected_identity=identity)
        recovery = ContinuationConsumer(identity).reconcile(lambda _: observation)
        assert recovery.action == "return_stored_result"
        assert recovery.stored_result == status["storedResult"]
        assert recovery.stored_result == f"created {status['matchingIds'][0]}"
        assert recovery.fresh_write_authorized is False
    finally:
        restarted.close()

    with closing(IssueStore(str(db), backend_id=BACKEND)) as store:
        record = store.operation_record(identity)
        assert record is not None and record.result == recovery.stored_result
        assert store.count() == store.operation_count() == 1
    transcript = (tmp_path / "restarted.transcript.log").read_text()
    requests = [json.loads(line[2:]) for line in transcript.splitlines() if line.startswith("> ")]
    assert [r["params"]["name"] for r in requests if r.get("method") == "tools/call"] == [
        "get_operation_status"
    ]


def test_partial_first_commit_crash_keeps_unresolved_effect(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    args = _args("next-partial", mode="partial")
    identity = OperationIdentity(args["operation_id"], "alice", BACKEND)
    crashed = _spawn(tmp_path, db, "crashed", fault="exit-after-partial-first-commit")
    token = _round_one(crashed, args)
    with pytest.raises(WireError):
        _commit(crashed, args, token, req_id=11)
    assert crashed.returncode == 73
    crashed.close()

    restarted = _spawn(tmp_path, db, "restarted")
    try:
        status = _status(restarted, identity, 12)
        observation = observation_from_wire(status, expected_identity=identity)
        recovery = ContinuationConsumer(identity).reconcile(lambda _: observation)
        assert recovery.effect == "unknown" and recovery.action == "stop"
        assert status["storedResult"] is None
        with pytest.raises(WireError, match="operation_in_progress"):
            _commit(restarted, args, token, req_id=13)
    finally:
        restarted.close()

    with closing(IssueStore(str(db), backend_id=BACKEND)) as store:
        record = store.operation_record(identity)
        assert record is not None and record.state == "in_progress"
        assert record.effect_id is not None and store.get_issue(record.effect_id) is not None
        assert store.count() == store.operation_count() == 1
        assert store.watchers_for(record.effect_id) == []
        assert store.compensations_for(record.effect_id) == []


@pytest.mark.parametrize(
    ("change", "error"),
    [
        ({"storedResult": None}, "stored result"),
        ({"storedResult": 3}, "stored result"),
        (
            {"scopeBinding": {"operationId": "other", "principal": "alice", "backend": BACKEND}},
            "scope",
        ),
        ({"state": "unknown", "matchingIds": []}, "unsettled"),
        ({"matchingIds": [2]}, "disagrees"),
    ],
)
def test_inconsistent_status_cannot_return_result(change: dict, error: str) -> None:
    identity = OperationIdentity("test", "alice", BACKEND)
    value = {
        "operationId": "test",
        "principal": "alice",
        "backend": BACKEND,
        "scopeBinding": {"operationId": "test", "principal": "alice", "backend": BACKEND},
        "observedAt": "2000-01-01T00:00:00+00:00",
        "authoritative": True,
        "freshWriteAuthorized": False,
        "scope": "diagnostic text can vary",
        "state": "applied",
        "matchingIds": [1],
        "detail": "",
        "storedResult": "created 1",
    }
    value.update(change)
    with pytest.raises(ValueError, match=error):
        observation_from_wire(value, expected_identity=identity)


def test_old_terminal_observation_can_remain_valid() -> None:
    identity = OperationIdentity("test", "alice", BACKEND)
    value = {
        "operationId": "test",
        "principal": "alice",
        "backend": BACKEND,
        "scopeBinding": {"operationId": "test", "principal": "alice", "backend": BACKEND},
        "observedAt": "2000-01-01T00:00:00+00:00",
        "authoritative": True,
        "freshWriteAuthorized": False,
        "scope": "diagnostic text",
        "state": "applied",
        "matchingIds": [1],
        "storedResult": "created 1",
    }
    observed = observation_from_wire(value, expected_identity=identity)
    assert ContinuationConsumer(identity).reconcile(lambda _: observed).stored_result == "created 1"


@pytest.mark.parametrize(
    "change",
    [
        {"authoritative": 1},
        {"state": "invalid"},
        {"matching_ids": (True,)},
        {"matching_ids": (-1,)},
        {"observed_at": "2000-01-01T00:00:00"},
        {"scope_binding": None},
        {"stored_result": "created 2"},
    ],
)
def test_direct_consumer_rejects_malformed_authoritative_observation(change: dict) -> None:
    identity = OperationIdentity("test", "alice", BACKEND)
    good = EffectObservation(
        identity=identity,
        observed_at="2000-01-01T00:00:00+00:00",
        authoritative=True,
        scope="diagnostic text",
        scope_binding=identity,
        state="applied",
        matching_ids=(1,),
        stored_result="created 1",
    )
    with pytest.raises(ValueError):
        ContinuationConsumer(identity).reconcile(lambda _: replace(good, **change))
