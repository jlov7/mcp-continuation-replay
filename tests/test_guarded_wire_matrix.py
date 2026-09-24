"""Frozen twelve-case guarded stdio completion matrix.

The tests exercise a real consumer and raw JSON-RPC subprocesses. When
``MATRIX_EVIDENCE_JSONL`` is set, each passing case appends one sanitized
machine-readable record; absent records make the separate evidence verifier
fail closed.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

import pytest

from reference.backend import IssueStore, OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.readback import ReadBack
from reference.wire_recovery import observation_from_wire
from tests.wire_client import RawStdioClient, WireError

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "reference" / "guarded_server_stdio.py"
BACKEND = "sqlite:guarded-matrix"
T0 = 1_790_035_200
STATE_KEY_HEX = hashlib.sha256(b"synthetic guarded matrix state key").hexdigest()
FINGERPRINT_KEY_HEX = hashlib.sha256(b"synthetic guarded matrix fingerprint key").hexdigest()


def _case_dir(tmp_path: Path, case_id: str) -> Path:
    configured = os.environ.get("MATRIX_ARTIFACT_DIR")
    if configured:
        path = Path(configured) / f"case-{case_id}"
        path.mkdir(parents=False, exist_ok=False)
        return path
    path = tmp_path / f"case-{case_id}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def _spawn(
    case_dir: Path,
    db: Path,
    name: str,
    *,
    principal: str = "alice",
    clock: int = T0,
    authority_ttl: int = 300,
    replay_ttl: int = 360,
    request_state_ttl: int = 600,
    fault: str = "",
) -> RawStdioClient:
    extra = {
        "WIRE_PRINCIPAL": principal,
        "WIRE_CLOCK_EPOCH": str(clock),
        "WIRE_AUTHORITY_TTL": str(authority_ttl),
        "WIRE_REPLAY_RETENTION_TTL": str(replay_ttl),
        "WIRE_REQUEST_STATE_TTL": str(request_state_ttl),
        "WIRE_STATE_KEY_HEX": STATE_KEY_HEX,
        "WIRE_FINGERPRINT_KEY_HEX": FINGERPRINT_KEY_HEX,
    }
    if fault:
        extra["WIRE_FAULT"] = fault
    wire = RawStdioClient(
        [sys.executable, str(SERVER)],
        case_dir / f"{name}.transcript.log",
        db,
        timeout_s=8,
        extra_env=extra,
        backend_id=BACKEND,
    )
    wire.open_connection()
    return wire


def _args(case_id: str, *, mode: str = "atomic") -> dict[str, str]:
    return {"operation_id": f"case-{case_id}", "title": f"guarded-{case_id}", "mode": mode}


def _round_one(wire: RawStdioClient, arguments: dict[str, str], req_id: int = 10) -> str:
    result = wire.request(
        "tools/call", {"name": "create_guarded_issue", "arguments": arguments}, req_id
    )
    assert result.get("resultType") == "input_required"
    assert isinstance(result.get("requestState"), str)
    return str(result["requestState"])


def _commit(
    wire: RawStdioClient,
    arguments: dict[str, str],
    token: str | None,
    body: str = "alpha",
    req_id: int = 20,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "name": "create_guarded_issue",
        "arguments": arguments,
        "inputResponses": {"body": {"action": "accept", "content": {"body": body}}},
    }
    if token is not None:
        params["requestState"] = token
    return wire.request("tools/call", params, req_id)


def _structured(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("structuredContent")
    assert isinstance(content, dict), f"missing structured result: {result!r}"
    return content


def _wire_observe(wire: RawStdioClient, identity: OperationIdentity, req_id: int) -> Any:
    result = wire.request(
        "tools/call",
        {"name": "get_operation_status", "arguments": {"operation_id": identity.operation_id}},
        req_id,
    )
    return observation_from_wire(_structured(result), expected_identity=identity)


def _rejects(call: Any, mechanism: str) -> str:
    with pytest.raises(WireError) as caught:
        call()
    message = str(caught.value)
    assert mechanism in message, message
    return mechanism


def _record(case_id: str, facts: dict[str, Any], paths: list[str | Path], exit_codes: list[int]) -> None:
    target = os.environ.get("MATRIX_EVIDENCE_JSONL")
    if target is None:
        return
    record = {
        "case_id": case_id,
        "status": "pass",
        "observed": facts,
        "process_exit_codes": exit_codes,
        "artifacts": [Path(path).resolve().relative_to(ROOT).as_posix() for path in paths],
    }
    with Path(target).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def _close(wire: RawStdioClient) -> int:
    wire.close()
    code = wire.returncode
    assert code is not None
    return code


def test_guarded_case_01_identical_retry_returns_stored_result(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "01")
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    args = _args("01")
    try:
        token = _round_one(wire, args)
        first = _structured(_commit(wire, args, token, req_id=11))
        second = _structured(_commit(wire, args, token, req_id=12))
        assert first["result"] == second["result"]
        assert [first["replayed"], second["replayed"]] == [False, True]
    finally:
        code = _close(wire)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == store.operation_count() == 1
    finally:
        store.close()
    _record("01", {"effects": 1, "operations": 1, "replayed": True}, [wire._t.name, db], [code])


def test_guarded_case_02_never_admitted_remains_unknown(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "02")
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    try:
        _round_one(wire, _args("02"))
    finally:
        code = _close(wire)
    store = IssueStore(str(db), backend_id=BACKEND)
    identity = OperationIdentity("case-02", "alice", BACKEND)
    try:
        consumer = ContinuationConsumer(identity)
        settled = consumer.reconcile(ReadBack(store, principal="alice").reconcile_operation)
        assert settled.effect == "unknown" and settled.action == "stop"
        assert settled.fresh_write_authorized is False
        assert store.count() == store.operation_count() == 0
    finally:
        store.close()
    _record("02", {"effect": "unknown", "action": "stop", "effects": 0}, [wire._t.name, db], [code])


def test_guarded_case_03_lost_reply_explicit_replay_is_one_effect(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "03")
    db = case / "store.sqlite3"
    args = _args("03")
    crashed = _spawn(case, db, "crash", fault="drop-after-commit")
    token = _round_one(crashed, args)
    consumer = ContinuationConsumer(OperationIdentity("case-03", "alice", BACKEND))
    with pytest.raises(WireError) as caught:
        _commit(crashed, args, token, req_id=11)
    uncertain = consumer.transport_failed(caught.value)
    assert uncertain.effect == "unknown" and uncertain.action == "reconcile"
    crash_code = crashed.returncode
    assert crash_code == 70

    live = _spawn(case, db, "restart")
    try:
        settled = consumer.reconcile(lambda identity: _wire_observe(live, identity, 12))
        assert settled.effect == "applied" and settled.action == "return_stored_result"
        replay = _structured(_commit(live, args, token, req_id=13))
        assert replay["replayed"] is True
    finally:
        live_code = _close(live)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == 1
    finally:
        store.close()
    _record(
        "03",
        {"transport": "unknown", "reconciled": "applied", "effects": 1, "replayed": True},
        [crashed._t.name, live._t.name, db],
        [crash_code, live_code],
    )


def test_guarded_case_04_changed_input_conflicts(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "04")
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    args = _args("04")
    try:
        token = _round_one(wire, args)
        _commit(wire, args, token, "alpha", 11)
        mechanism = _rejects(lambda: _commit(wire, args, token, "beta", 12), "operation_conflict")
    finally:
        code = _close(wire)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == 1 and len(store.issues_with_body("beta")) == 0
    finally:
        store.close()
    _record("04", {"mechanism": mechanism, "effects": 1}, [wire._t.name, db], [code])


def test_guarded_case_05_changed_valid_request_state_conflicts(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "05")
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    args = _args("05")
    try:
        first_token = _round_one(wire, args, 10)
        second_token = _round_one(wire, args, 11)
        assert first_token != second_token
        _commit(wire, args, first_token, req_id=12)
        mechanism = _rejects(
            lambda: _commit(wire, args, second_token, req_id=13), "operation_conflict"
        )
        mutation_index = len(second_token) // 2
        tampered = (
            second_token[:mutation_index]
            + ("A" if second_token[mutation_index] != "A" else "B")
            + second_token[mutation_index + 1 :]
        )
        assert tampered != second_token and tampered[:3] == second_token[:3] == "v1."
        boundary = _rejects(
            lambda: _commit(wire, args, tampered, req_id=14), "Invalid or expired requestState"
        )
    finally:
        code = _close(wire)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == 1
    finally:
        store.close()
    _record(
        "05",
        {"valid_changed_state": mechanism, "tampered_state": boundary, "effects": 1},
        [wire._t.name, db],
        [code],
    )


def test_guarded_case_06_principal_is_server_bound(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "06")
    db = case / "store.sqlite3"
    args = _args("06")
    alice = _spawn(case, db, "alice", principal="alice")
    token = _round_one(alice, args)
    _commit(alice, args, token, req_id=11)
    alice_code = _close(alice)

    bob = _spawn(case, db, "bob", principal="bob")
    try:
        boundary = _rejects(
            lambda: _commit(bob, args, token, req_id=12), "Invalid or expired requestState"
        )
        bob_token = _round_one(bob, args, 13)
        ledger = _rejects(lambda: _commit(bob, args, bob_token, req_id=14), "operation_conflict")
    finally:
        bob_code = _close(bob)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        with pytest.raises(ValueError, match="principal"):
            ReadBack(store, principal="bob").reconcile_operation(
                OperationIdentity("case-06", "alice", BACKEND)
            )
        assert store.count() == 1
    finally:
        store.close()
    _record(
        "06",
        {"sdk_principal_binding": boundary, "ledger_binding": ledger, "effects": 1},
        [alice._t.name, bob._t.name, db],
        [alice_code, bob_code],
    )


def test_guarded_case_07_expired_authority_rejects_write_but_allows_readback(
    tmp_path: Path,
) -> None:
    case = _case_dir(tmp_path, "07")
    db = case / "store.sqlite3"
    args = _args("07")
    current = _spawn(case, db, "current", authority_ttl=60, replay_ttl=360)
    token = _round_one(current, args)
    _commit(current, args, token, req_id=11)
    current_code = _close(current)

    expired = _spawn(
        case, db, "after-authority-expiry", clock=T0 + 120, authority_ttl=60, replay_ttl=360
    )
    try:
        mechanism = _rejects(
            lambda: _commit(expired, args, token, req_id=12), "operation_authority_expired"
        )
        identity = OperationIdentity("case-07", "alice", BACKEND)
        settled = ContinuationConsumer(identity).reconcile(
            lambda expected: _wire_observe(expired, expected, 13)
        )
        assert settled.effect == "applied"
        assert settled.action == "return_stored_result"
        assert settled.fresh_write_authorized is False
    finally:
        expired_code = _close(expired)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == 1
    finally:
        store.close()
    _record(
        "07",
        {"mechanism": mechanism, "readback": "applied", "fresh_write_authorized": False},
        [current._t.name, expired._t.name, db],
        [current_code, expired_code],
    )


def test_guarded_case_08_independent_processes_serialize_identical_attempts(
    tmp_path: Path,
) -> None:
    case = _case_dir(tmp_path, "08")
    db = case / "store.sqlite3"
    args = _args("08")
    issuer = _spawn(case, db, "issuer")
    token = _round_one(issuer, args)
    issuer_code = _close(issuer)
    first = _spawn(case, db, "worker-a")
    second = _spawn(case, db, "worker-b")
    barrier = threading.Barrier(3)
    results: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def run(wire: RawStdioClient, req_id: int) -> None:
        try:
            barrier.wait(timeout=5)
            results.append(_structured(_commit(wire, args, token, req_id=req_id)))
        except Exception as exc:  # noqa: BLE001 - preserve worker failure for parent assertion
            errors.append(exc)

    threads = [
        threading.Thread(target=run, args=(first, 21)),
        threading.Thread(target=run, args=(second, 22)),
    ]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=5)
    for thread in threads:
        thread.join(timeout=10)
    assert all(not thread.is_alive() for thread in threads)
    assert not errors, errors
    assert len(results) == 2
    assert sorted(result["replayed"] for result in results) == [False, True]
    assert len({result["result"] for result in results}) == 1
    first_code, second_code = _close(first), _close(second)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == store.operation_count() == 1
    finally:
        store.close()
    _record(
        "08",
        {"barrier_parties": 3, "processes": 2, "replayed_flags": [False, True], "effects": 1},
        [issuer._t.name, first._t.name, second._t.name, db],
        [issuer_code, first_code, second_code],
    )


def test_guarded_case_09_crash_reconciles_without_redispatch(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "09")
    db = case / "store.sqlite3"
    args = _args("09")
    wire = _spawn(case, db, "crash", fault="drop-after-commit")
    token = _round_one(wire, args)
    consumer = ContinuationConsumer(OperationIdentity("case-09", "alice", BACKEND))
    with pytest.raises(WireError) as caught:
        _commit(wire, args, token, req_id=11)
    uncertain = consumer.transport_failed(caught.value)
    assert uncertain.action == "reconcile" and uncertain.effect == "unknown"
    crash_code = wire.returncode
    assert crash_code == 70
    restarted = _spawn(case, db, "restart")
    try:
        settled = consumer.reconcile(lambda identity: _wire_observe(restarted, identity, 12))
        assert settled.effect == "applied" and settled.action == "return_stored_result"
    finally:
        restart_code = _close(restarted)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == 1
    finally:
        store.close()
    _record(
        "09",
        {"crash_exit": 70, "transport": "unknown", "reconciled": "applied", "effects": 1},
        [wire._t.name, restarted._t.name, db],
        [crash_code, restart_code],
    )


def test_guarded_case_10_retention_and_sdk_expiry_keep_tombstone(tmp_path: Path) -> None:
    case = _case_dir(tmp_path, "10")
    db = case / "store.sqlite3"
    args = _args("10")
    current = _spawn(case, db, "current", authority_ttl=360, replay_ttl=60)
    token = _round_one(current, args)
    _commit(current, args, token, req_id=11)
    current_code = _close(current)

    retained = _spawn(case, db, "after-retention", clock=T0 + 120, authority_ttl=360, replay_ttl=60)
    try:
        app_expiry = _rejects(
            lambda: _commit(retained, args, token, req_id=12), "operation_retention_expired"
        )
        fresh = _round_one(retained, args, 13)
        tombstone = _rejects(
            lambda: _commit(retained, args, fresh, req_id=14), "operation_conflict"
        )
    finally:
        retained_code = _close(retained)

    sdk_expired = _spawn(
        case, db, "after-sdk-expiry", clock=T0 + 660, authority_ttl=360, replay_ttl=60
    )
    try:
        sdk_expiry = _rejects(
            lambda: _commit(sdk_expired, args, token, req_id=15),
            "Invalid or expired requestState",
        )
    finally:
        sdk_code = _close(sdk_expired)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == store.operation_count() == 1
    finally:
        store.close()
    _record(
        "10",
        {
            "application_expiry": app_expiry,
            "sdk_expiry": sdk_expiry,
            "fresh_issuance": tombstone,
            "effects": 1,
            "operations": 1,
        },
        [current._t.name, retained._t.name, sdk_expired._t.name, db],
        [current_code, retained_code, sdk_code],
    )


def test_guarded_case_11_stripped_state_is_unsupported_not_new_operation(
    tmp_path: Path,
) -> None:
    case = _case_dir(tmp_path, "11")
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    args = _args("11")
    try:
        _round_one(wire, args)
        mechanism = _rejects(
            lambda: _commit(wire, args, None, req_id=11), "unsupported continuation"
        )
        valid_new = _round_one(wire, _args("11-new"), 12)
        assert valid_new
    finally:
        code = _close(wire)
    store = IssueStore(str(db), backend_id=BACKEND)
    try:
        assert store.count() == store.operation_count() == 0
    finally:
        store.close()
    _record(
        "11",
        {"mechanism": mechanism, "valid_initial_round": "input_required", "effects": 0},
        [wire._t.name, db],
        [code],
    )


def test_guarded_case_12_partial_and_failed_compensation_are_durable(
    tmp_path: Path,
) -> None:
    case = _case_dir(tmp_path, "12")
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    args = _args("12", mode="partial")
    try:
        token = _round_one(wire, args)
        first = _structured(_commit(wire, args, token, req_id=11))
        replay = _structured(_commit(wire, args, token, req_id=12))
        assert first["state"] == replay["state"] == "partial"
        assert first["replayed"] is False and replay["replayed"] is True
    finally:
        code = _close(wire)
    store = IssueStore(str(db), backend_id=BACKEND)
    identity = OperationIdentity("case-12", "alice", BACKEND)
    try:
        readback = ReadBack(store, principal="alice")
        observed = readback.reconcile_operation(identity)
        assert observed.state == "partial" and observed.effects == 1
        assert store.watchers_for(observed.matching_ids[0]) == []
        compensations = store.compensations_for(observed.matching_ids[0])
        assert len(compensations) == 1
        assert compensations[0].kind == "rollback_issue"
        assert compensations[0].outcome == "failed:SyntheticCompensationFailure"
        events = store.operation_events("case-12")
        assert [(event.step, event.outcome, event.error_type) for event in events] == [
            ("watcher", "attempted", None),
            ("watcher", "failed", "SyntheticWatcherFailure"),
            ("rollback_issue", "attempted", None),
            ("rollback_issue", "failed", "SyntheticCompensationFailure"),
        ]
        settled = ContinuationConsumer(identity).reconcile(readback.reconcile_operation)
        assert settled.action == "stop" and settled.fresh_write_authorized is False
        assert store.count() == store.operation_count() == 1
    finally:
        store.close()
    _record(
        "12",
        {
            "state": "partial",
            "effects": 1,
            "watchers": 0,
            "failed_compensations": 1,
            "step_events": 4,
            "replayed": True,
        },
        [wire._t.name, db],
        [code],
    )
