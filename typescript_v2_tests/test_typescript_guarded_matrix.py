"""Run the frozen Python semantic assertions against stable TypeScript v2 stdio.

The assertions and consumer are shared deliberately. The server transport,
SDK request-state codec, and raw replies are TypeScript v2; SQLite mediation
uses the disclosed Python bridge.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest

from reference.backend import OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.typescript_guarded_bridge import _state
from reference.wire_recovery import observation_from_wire
from tests import test_guarded_wire_matrix as semantic
from tests.wire_client import RawStdioClient, WireError

SERVER = semantic.ROOT / "reference" / "typescript_guarded_server.cjs"


class TypeScriptV2Client(RawStdioClient):
    def _frame(self, method: str, params: dict, req_id: int) -> dict:
        frame = super()._frame(method, params, req_id)
        frame["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"] = {
            "elicitation": {"form": {}}
        }
        return frame

    def request(self, method: str, params: dict, req_id: int | None = None) -> dict:
        result = super().request(method, params, req_id)
        if result.get("isError") is True:
            content = result.get("content", [])
            messages = [part.get("text", "") for part in content if isinstance(part, dict)]
            raise WireError(f"tool error for {method}: {' '.join(messages)}")
        return result


def _spawn(
    case_dir: Path,
    db: Path,
    name: str,
    *,
    principal: str = "alice",
    clock: int = semantic.T0,
    authority_ttl: int = 300,
    replay_ttl: int = 360,
    request_state_ttl: int = 600,
    fault: str = "",
) -> RawStdioClient:
    node_modules = os.environ.get("TS_V2_NODE_MODULES")
    if not node_modules or not (Path(node_modules) / "@modelcontextprotocol/server/package.json").is_file():
        raise RuntimeError("TS_V2_NODE_MODULES must identify the isolated installed v2 packages")
    env = {
        "WIRE_PRINCIPAL": principal,
        "WIRE_CLOCK_EPOCH": str(clock),
        "WIRE_AUTHORITY_TTL": str(authority_ttl),
        "WIRE_REPLAY_RETENTION_TTL": str(replay_ttl),
        "WIRE_REQUEST_STATE_TTL": str(request_state_ttl),
        "WIRE_STATE_KEY_HEX": semantic.STATE_KEY_HEX,
        "WIRE_FINGERPRINT_KEY_HEX": semantic.FINGERPRINT_KEY_HEX,
    }
    if fault:
        env["WIRE_FAULT"] = fault
    wire = TypeScriptV2Client(
        ["env", f"NODE_PATH={Path(node_modules).resolve()}", "node", str(SERVER)],
        case_dir / f"{name}.transcript.log",
        db,
        timeout_s=8,
        extra_env=env,
        backend_id=semantic.BACKEND,
    )
    wire.open_connection()
    return wire


def _rejects(call: Callable[[], Any], mechanism: str) -> str:
    with pytest.raises(WireError) as caught:
        call()
    message = str(caught.value)
    if mechanism == "Invalid or expired requestState":
        assert "-32602" in message and ("requestState" in message or "request state" in message)
        return "sdk_state_rejected"
    assert mechanism in message, message
    return mechanism


def _run(monkeypatch: pytest.MonkeyPatch, test: Callable[[Path], None], tmp_path: Path) -> None:
    monkeypatch.setattr(semantic, "_spawn", _spawn)
    monkeypatch.setattr(semantic, "_rejects", _rejects)
    test(tmp_path)


def _case(tmp_path: Path, case_id: str) -> tuple[Path, Path]:
    configured = os.environ.get("MATRIX_ARTIFACT_DIR")
    path = (Path(configured) if configured else tmp_path) / f"case-{case_id}"
    return path, path / "store.sqlite3"


def _extend_record(path: Path, code: int) -> None:
    target = os.environ.get("MATRIX_EVIDENCE_JSONL")
    if not target:
        return
    record_path = Path(target)
    record = json.loads(record_path.read_text())
    record["artifacts"].append(path.resolve().relative_to(semantic.ROOT).as_posix())
    record["process_exit_codes"].append(code)
    record_path.write_text(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


@pytest.mark.parametrize(
    "extra",
    [
        {"body": {"action": "accept", "content": {"body": "alpha", "other": "value"}}},
        {"body": {"action": "accept", "content": {"body": "alpha"}, "other": "value"}},
        {"body": {"action": "accept", "content": {"body": "alpha"}, "_meta": {"trace": "value"}}},
        {"body": {"action": "accept", "content": {"body": "alpha"}}, "other": {"action": "accept"}},
    ],
)
def test_extra_accepted_response_fields_rejected_before_effect(tmp_path: Path, extra: dict) -> None:
    case = tmp_path / "response-shape"
    case.mkdir()
    db = case / "store.sqlite3"
    wire = _spawn(case, db, "server")
    args = semantic._args("shape")
    try:
        token = semantic._round_one(wire, args)
        with pytest.raises(WireError):
            wire.request(
                "tools/call",
                {"name": "create_guarded_issue", "arguments": args, "requestState": token, "inputResponses": extra},
                11,
            )
        with closing(sqlite3.connect(db)) as conn:
            assert conn.execute("SELECT count(*) FROM issues").fetchone() == (0,)
            assert conn.execute("SELECT count(*) FROM operations").fetchone() == (0,)
        accepted = semantic._structured(semantic._commit(wire, args, token, req_id=12))
        assert accepted["replayed"] is False
    finally:
        semantic._close(wire)


def test_bridge_rejects_boolean_request_state_version() -> None:
    state = {
        "v": True, "operation_id": "case-shape", "nonce": "synthetic",
        "issued_at": semantic.T0, "authority_expires_at": semantic.T0 + 300,
        "replay_expires_at": semantic.T0 + 360,
    }
    with pytest.raises(ValueError, match="requestState"):
        _state(state, "case-shape", semantic.T0)


def test_guarded_ts_case_01(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_01_identical_retry_returns_stored_result, tmp_path)


def test_guarded_ts_case_02(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_02_never_admitted_remains_unknown, tmp_path)
    case, db = _case(tmp_path, "02")
    wire = _spawn(case, db, "readback")
    try:
        identity = OperationIdentity("case-02", "alice", semantic.BACKEND)
        settled = ContinuationConsumer(identity).reconcile(
            lambda expected: semantic._wire_observe(wire, expected, 21)
        )
        assert settled.effect == "unknown" and settled.action == "stop"
    finally:
        code = semantic._close(wire)
    _extend_record(Path(wire._t.name), code)


def test_guarded_ts_case_03(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_03_lost_reply_explicit_replay_is_one_effect, tmp_path)


def test_guarded_ts_case_04(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_04_changed_input_conflicts, tmp_path)


def test_guarded_ts_case_05(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_05_changed_valid_request_state_conflicts, tmp_path)


def test_guarded_ts_case_06(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_06_principal_is_server_bound, tmp_path)
    case, db = _case(tmp_path, "06")
    bob = _spawn(case, db, "bob-readback", principal="bob")
    try:
        identity = OperationIdentity("case-06", "alice", semantic.BACKEND)
        result = bob.request(
            "tools/call", {"name": "get_operation_status", "arguments": {"operation_id": "case-06"}}, 21
        )
        status = semantic._structured(result)
        assert status["principal"] == "bob" and status["state"] == "unknown"
        with pytest.raises(ValueError, match="identity"):
            observation_from_wire(status, expected_identity=identity)
    finally:
        code = semantic._close(bob)
    _extend_record(Path(bob._t.name), code)


def test_guarded_ts_case_07(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_07_expired_authority_rejects_write_but_allows_readback, tmp_path)


def test_guarded_ts_case_08(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_08_independent_processes_serialize_identical_attempts, tmp_path)


def test_guarded_ts_case_09(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_09_crash_reconciles_without_redispatch, tmp_path)


def test_guarded_ts_case_10(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_10_retention_and_sdk_expiry_keep_tombstone, tmp_path)


def test_guarded_ts_case_11(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_11_stripped_state_is_unsupported_not_new_operation, tmp_path)


def test_guarded_ts_case_12(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _run(monkeypatch, semantic.test_guarded_case_12_partial_and_failed_compensation_are_durable, tmp_path)
    case, db = _case(tmp_path, "12")
    wire = _spawn(case, db, "readback")
    try:
        identity = OperationIdentity("case-12", "alice", semantic.BACKEND)
        settled = ContinuationConsumer(identity).reconcile(
            lambda expected: semantic._wire_observe(wire, expected, 21)
        )
        assert settled.effect == "partial" and settled.action == "stop"
    finally:
        code = semantic._close(wire)
    _extend_record(Path(wire._t.name), code)
