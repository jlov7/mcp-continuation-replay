"""Run and independently verify the frozen guarded stdio matrix.

Each invocation creates a new attempt. Failed attempts remain available for
inspection; this command never deletes or overwrites prior evidence.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "research-completion-2026-09-22"
SPEC = DOC / "matrix-spec.json"
TESTS = ROOT / "tests" / "test_guarded_wire_matrix.py"
SOURCE = [
    ROOT / "reference" / name
    for name in ("backend.py", "consumer.py", "readback.py", "guarded_server_stdio.py", "wire_recovery.py")
] + [
    TESTS, ROOT / "tests" / "wire_client.py", ROOT / "tests" / "test_matrix_evidence_gate.py",
    Path(__file__).resolve(), ROOT / "scripts" / "current_typescript_mrtr_server.cjs",
    ROOT / "scripts" / "probe_current_typescript_sdk.py", ROOT / "tests" / "coverage_startup" / "sitecustomize.py", SPEC, DOC / "PROTOCOL.md",
]
BASE_ENV_NAMES = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
GUARDED_ENV_NAMES = (
    "WIRE_SERVER_DB", "WIRE_BACKEND_ID", "WIRE_PRINCIPAL", "WIRE_CLOCK_EPOCH",
    "WIRE_AUTHORITY_TTL", "WIRE_REPLAY_RETENTION_TTL", "WIRE_REQUEST_STATE_TTL",
    "WIRE_STATE_KEY_HEX", "WIRE_FINGERPRINT_KEY_HEX", "WIRE_FAULT",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def test_inventory() -> dict[str, str]:
    tree = ast.parse(TESTS.read_text(encoding="utf-8"))
    result: dict[str, str] = {}
    for item in tree.body:
        if isinstance(item, ast.FunctionDef) and item.name.startswith("test_guarded_case_"):
            case_id = item.name.removeprefix("test_guarded_case_")[:2]
            if case_id in result:
                raise ValueError(f"duplicate test for case {case_id}")
            result[case_id] = item.name
    return result


def db_facts(path: Path) -> dict[str, Any]:
    uri = f"file:{path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        db.row_factory = sqlite3.Row
        def rows(sql: str) -> list[dict[str, Any]]:
            return [dict(row) for row in db.execute(sql).fetchall()]
        return {
            "issues": rows("SELECT id, title, body FROM issues ORDER BY id"),
            "operations": rows("SELECT operation_id, principal, backend, state, effect_id, result, issued_at, authority_expires_at, replay_expires_at FROM operations ORDER BY operation_id, principal"),
            "watchers": rows("SELECT issue_id, name FROM watchers ORDER BY id"),
            "compensations": rows("SELECT issue_id, kind, outcome FROM compensations ORDER BY id"),
            "events": rows("SELECT operation_id, step, outcome, error_type FROM operation_events ORDER BY id"),
        }


def wire_facts(paths: list[Path]) -> dict[str, Any]:
    calls: list[dict[str, Any]] = []
    replies: list[dict[str, Any]] = []
    versions: set[str] = set()
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if len(line) < 3 or line[:2] not in {"> ", "< "}:
                raise ValueError(f"malformed transcript line in {path.name}")
            obj = json.loads(line[2:])
            if line.startswith("> ") and obj.get("method") == "tools/call":
                params = obj.get("params", {})
                versions.add(params.get("_meta", {}).get("io.modelcontextprotocol/protocolVersion", "missing"))
                calls.append({"source": path.name, "id": obj.get("id"), "tool": params.get("name"), "continuation": "inputResponses" in params, "state_present": "requestState" in params})
            elif line.startswith("> ") and obj.get("method") == "tools/list":
                versions.add(obj.get("params", {}).get("_meta", {}).get("io.modelcontextprotocol/protocolVersion", "missing"))
            elif line.startswith("< "):
                replies.append({"source": path.name, "id": obj.get("id"), "error": obj.get("error", {}).get("message") if isinstance(obj.get("error"), dict) else None, "result_type": obj.get("result", {}).get("resultType") if isinstance(obj.get("result"), dict) else None, "structured": obj.get("result", {}).get("structuredContent") if isinstance(obj.get("result"), dict) else None})
    return {"calls": calls, "replies": replies, "request_protocol_versions": sorted(versions), "handshake": "modern per-request envelope; no initialize"}


def predicate(case_id: str, db: dict[str, Any], wire: dict[str, Any], exit_codes: list[int]) -> None:
    issues, operations = db["issues"], db["operations"]
    expected_count = 0 if case_id in {"02", "11"} else 1
    assert len(issues) == len(operations) == expected_count, (case_id, db)
    if expected_count:
        assert operations[0]["operation_id"] == f"case-{case_id}"
        assert operations[0]["principal"] == "alice"
        assert operations[0]["backend"] == "sqlite:guarded-matrix"
        assert operations[0]["effect_id"] == issues[0]["id"]
        assert issues[0]["title"] == f"guarded-{case_id}"
    if case_id == "12":
        assert operations[0]["state"] == "partial"
        assert db["watchers"] == []
        assert len(db["compensations"]) == 1
        assert db["compensations"][0]["outcome"] == "failed:SyntheticCompensationFailure"
        assert [(event["step"], event["outcome"], event["error_type"]) for event in db["events"]] == [
            ("watcher", "attempted", None), ("watcher", "failed", "SyntheticWatcherFailure"),
            ("rollback_issue", "attempted", None), ("rollback_issue", "failed", "SyntheticCompensationFailure"),
        ]
    else:
        assert db["watchers"] == db["compensations"] == db["events"] == []
        if expected_count:
            assert operations[0]["state"] == "applied"
    guarded = [call for call in wire["calls"] if call["tool"] == "create_guarded_issue"]
    assert wire["request_protocol_versions"] == ["2026-07-28"]
    assert guarded, case_id
    continuation_count = sum(call["continuation"] for call in guarded)
    assert continuation_count >= (2 if case_id in {"01", "04", "05", "06", "07", "08", "10", "12"} else 1 if case_id in {"03", "09", "11"} else 0)
    if case_id == "11":
        assert any(call["continuation"] and not call["state_present"] for call in guarded)
    if case_id in {"03", "09"}:
        assert 70 in exit_codes
        assert any(call["tool"] == "get_operation_status" for call in wire["calls"])
    if case_id in {"02", "07"}:
        assert case_id == "07" or not any(call["continuation"] for call in guarded)
    if case_id == "08":
        assert len({call["source"] for call in guarded if call["continuation"]}) == 2
    if case_id == "05":
        assert continuation_count == 3
    if case_id == "10":
        assert continuation_count == 4
    if case_id == "12":
        assert continuation_count == 2
    reply_by_key = {(reply["source"], reply["id"]): reply for reply in wire["replies"]}
    continuation_replies = [
        reply_by_key[(call["source"], call["id"])]
        for call in guarded if call["continuation"] and (call["source"], call["id"]) in reply_by_key
    ]
    completes = [reply["structured"] for reply in continuation_replies if isinstance(reply["structured"], dict)]
    errors = [reply["error"] for reply in continuation_replies if reply["error"]]
    flags = sorted(item.get("replayed") for item in completes)
    if case_id in {"01", "08", "12"}:
        assert flags == [False, True]
        assert len({item.get("result") for item in completes}) == 1
    if case_id == "12":
        assert all(item.get("state") == "partial" for item in completes)
    if case_id == "03":
        assert flags == [True] and len(continuation_replies) == 1
    if case_id == "09":
        assert not continuation_replies
    required_errors = {
        "04": ["operation_conflict"],
        "05": ["operation_conflict", "Invalid or expired requestState"],
        "06": ["operation_conflict", "Invalid or expired requestState"],
        "07": ["operation_authority_expired"],
        "10": ["operation_retention_expired", "operation_conflict", "Invalid or expired requestState"],
        "11": ["unsupported continuation"],
    }.get(case_id, [])
    assert len(errors) == len(required_errors), (case_id, errors)
    for expected_error in required_errors:
        assert any(expected_error in error for error in errors), (case_id, expected_error, errors)
    if case_id in {"02", "03", "07", "09"}:
        statuses = [reply["structured"] for call in wire["calls"] if call["tool"] == "get_operation_status" for reply in [reply_by_key.get((call["source"], call["id"]), {})] if isinstance(reply.get("structured"), dict)]
        if case_id != "02":
            assert len(statuses) == 1
            status = statuses[0]
            assert status.get("state") == "applied" and status.get("authoritative") is True
            assert status.get("freshWriteAuthorized") is False
            assert status.get("matchingIds") == [issues[0]["id"]]
            assert (status.get("operationId"), status.get("principal"), status.get("backend")) == (f"case-{case_id}", "alice", "sqlite:guarded-matrix")


def verify(attempt: Path) -> dict[str, Any]:
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    expected = {case["id"]: case for case in spec["cases"]}
    records = [json.loads(line) for line in (attempt / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    actual = {record["case_id"]: record for record in records}
    assert len(actual) == len(records) == len(expected)
    assert set(actual) == set(expected)
    for case_id, record in actual.items():
        assert record["expected"] == expected[case_id]["expected"]
        assert record["status"] in {"pass", "fail", "unsupported", "machinery_error"}
        assert record["status"] == "pass", (case_id, record["status"])
        assert record["pytest_exit_code"] == 0
        assert record["source_hashes"] == {relative(path): digest(path) for path in SOURCE}
        for name, recorded_hash in record["artifact_hashes"].items():
            path = ROOT / name
            assert path.is_file() and digest(path) == recorded_hash, name
        case_dir = attempt / f"case-{case_id}"
        transcripts = sorted(case_dir.glob("*.transcript.log"))
        assert transcripts
        db = db_facts(case_dir / "store.sqlite3")
        wire = wire_facts(transcripts)
        assert db == record["independent_db"]
        assert wire == record["independent_wire"]
        predicate(case_id, db, wire, record["process_exit_codes"])
    return {"requested": len(expected), "executed": len(records), "passed": sum(record["status"] == "pass" for record in records)}


def run() -> Path:
    if sys.flags.optimize:
        raise RuntimeError("the evidence verifier requires normal Python assertions")
    source_head = subprocess.check_output(["git", "-c", "core.fsmonitor=false", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(["git", "-c", "core.fsmonitor=false", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True).strip()
    if dirty:
        raise RuntimeError("canonical matrix requires a clean committed source tree")
    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    expected = {case["id"]: case for case in spec["cases"]}
    tests = test_inventory()
    if set(tests) != set(expected):
        raise ValueError(f"test inventory differs from frozen protocol: {set(tests) ^ set(expected)}")
    attempt = DOC / "raw" / f"attempt-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{time.time_ns()}"
    attempt.mkdir(parents=True, exist_ok=False)
    hashes = {relative(path): digest(path) for path in SOURCE}
    sdk_modules = ("mcp.server.request_state", "mcp.server.mcpserver")
    sdk_hashes = {}
    for name in sdk_modules:
        module = importlib.util.find_spec(name)
        if module is None or module.origin is None:
            raise RuntimeError(f"missing installed SDK module: {name}")
        sdk_hashes[name] = digest(Path(module.origin))
    provenance = {
        "python": platform.python_version(), "platform": platform.platform(),
        "mcp_version": importlib.metadata.version("mcp"),
        "sdk_module_sha256": sdk_hashes,
        "source_hashes": hashes,
        "source_head": source_head,
        "protocol_commit": "a529c959f990520857f5644b21e4ff2531bed7c9",
        "environment_allowlist_names": list(BASE_ENV_NAMES + GUARDED_ENV_NAMES),
        "environment_values_recorded": False,
        "command_template": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_guarded_wire_matrix.py::TEST_NAME"],
    }
    (attempt / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    result_path = attempt / "results.jsonl"
    for case_id, case in expected.items():
        evidence_path = attempt / f"case-{case_id}.test-record.jsonl"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"tests/test_guarded_wire_matrix.py::{tests[case_id]}"]
        env = {name: os.environ[name] for name in BASE_ENV_NAMES if name in os.environ}
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(ROOT / "src")))
        env.update({"MATRIX_ARTIFACT_DIR": str(attempt), "MATRIX_EVIDENCE_JSONL": str(evidence_path)})
        try:
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45, check=False)
            code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            code = 124
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
            stderr += "\nMATRIX_CASE_TIMEOUT 45 seconds\n"
        (attempt / f"case-{case_id}.pytest.stdout.log").write_text(stdout)
        (attempt / f"case-{case_id}.pytest.stderr.log").write_text(stderr)
        record: dict[str, Any] = {
            "case_id": case_id, "expected": case["expected"],
            "status": "machinery_error", "pytest_exit_code": code,
            "command": ["python", *command[1:]], "source_hashes": hashes,
            "source_head": source_head,
            "process_exit_codes": [], "independent_db": None, "independent_wire": None,
            "artifact_hashes": {},
        }
        try:
            emitted = [json.loads(line) for line in evidence_path.read_text().splitlines()]
            assert len(emitted) == 1 and emitted[0]["case_id"] == case_id
            record["process_exit_codes"] = emitted[0]["process_exit_codes"]
            case_dir = attempt / f"case-{case_id}"
            transcripts = sorted(case_dir.glob("*.transcript.log"))
            record["independent_db"] = db_facts(case_dir / "store.sqlite3")
            record["independent_wire"] = wire_facts(transcripts)
            predicate(case_id, record["independent_db"], record["independent_wire"], record["process_exit_codes"])
            assert code == 0
            record["status"] = "pass"
        except Exception as exc:  # noqa: BLE001 - retain unexpected verifier failures as evidence
            record["status"] = "fail" if code == 0 else "machinery_error"
            record["verification_error"] = f"{type(exc).__name__}: {exc}"
        case_files = sorted((attempt / f"case-{case_id}").glob("*")) if (attempt / f"case-{case_id}").exists() else []
        artifacts = case_files + [attempt / f"case-{case_id}.pytest.stdout.log", attempt / f"case-{case_id}.pytest.stderr.log"]
        if evidence_path.exists():
            artifacts.append(evidence_path)
        record["artifact_hashes"] = {relative(path): digest(path) for path in artifacts if path.is_file()}
        with result_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    try:
        report = verify(attempt)
    except Exception as exc:  # noqa: BLE001 - failed full inventory is retained
        report = {"requested": len(expected), "executed": len(expected), "passed": 0, "verification_error": f"{type(exc).__name__}: {exc}"}
    (attempt / "SUMMARY.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if "verification_error" in report:
        raise RuntimeError(f"matrix verification failed; evidence retained at {relative(attempt)}: {report['verification_error']}")
    return attempt


def main() -> None:
    if sys.flags.optimize:
        raise RuntimeError("the evidence verifier requires normal Python assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", type=Path, help="verify one retained attempt")
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify.resolve()), sort_keys=True))
    else:
        attempt = run()
        print(relative(attempt))


if __name__ == "__main__":
    main()
