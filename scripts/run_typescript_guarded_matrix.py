"""Execute and independently verify the frozen additive TypeScript v2 matrix."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from scripts.run_completion_matrix import ROOT, db_facts, digest, predicate, relative, wire_facts

DOC = ROOT / "docs" / "research-completion-2026-09-22" / "typescript-v2"
INVENTORY = DOC / "inventory.json"
SDK_LOCK = DOC / "sdk-lock.json"
PYTHON_ATTEMPT = ROOT / "docs" / "research-completion-2026-09-22" / "raw" / "attempt-20260922T182510Z-1790101510523840000"
SOURCE = [
    ROOT / "reference" / "typescript_guarded_bridge.py",
    ROOT / "reference" / "typescript_guarded_server.cjs",
    ROOT / "reference" / "backend.py",
    ROOT / "reference" / "consumer.py",
    ROOT / "reference" / "readback.py",
    ROOT / "reference" / "wire_recovery.py",
    ROOT / "src" / "continuation_replay" / "fingerprint.py",
    ROOT / "tests" / "test_guarded_wire_matrix.py",
    ROOT / "typescript_v2_tests" / "test_typescript_guarded_matrix.py",
    ROOT / "tests" / "wire_client.py",
    ROOT / "scripts" / "run_completion_matrix.py",
    Path(__file__).resolve(), ROOT / "tests" / "coverage_startup" / "sitecustomize.py",
    DOC / "PROTOCOL.md", INVENTORY, SDK_LOCK,
    ROOT / "adapters" / "typescript-v2" / "package.json",
    ROOT / "adapters" / "typescript-v2" / "package-lock.json",
]
BASE_NAMES = ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")


def sdk_packages(node_modules: Path) -> dict[str, Any]:
    locked = json.loads(SDK_LOCK.read_text())["packages"]
    result: dict[str, Any] = {}
    for name in ("server", "core", "zod"):
        package = node_modules / ("@modelcontextprotocol" if name != "zod" else "") / name
        metadata = json.loads((package / "package.json").read_text())
        entry = package / "dist" / "index.cjs" if name != "zod" else package / "index.cjs"
        result[name] = {"version": metadata["version"], "module_sha256": digest(entry)}
    for name in ("server", "core", "zod"):
        identity = f"@modelcontextprotocol/{name}" if name != "zod" else "zod"
        key = "installed_dist_index_cjs_sha256" if name != "zod" else "installed_index_cjs_sha256"
        assert result[name] == {"version": locked[identity]["version"], "module_sha256": locked[identity][key]}
    return result


def ts_wire_facts(paths: list[Path]) -> dict[str, Any]:
    wire = wire_facts(paths)
    lookup = {(reply["source"], reply["id"]): reply for reply in wire["replies"]}
    error_shapes: list[dict[str, Any]] = []
    jsonrpc_errors: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.startswith("< "):
                continue
            message = json.loads(line[2:])
            if isinstance(message.get("error"), dict):
                error = message["error"]
                jsonrpc_errors.append({"source": path.name, "id": message.get("id"), "code": error.get("code"), "message": error.get("message")})
            result = message.get("result")
            if not isinstance(result, dict) or result.get("isError") is not True:
                continue
            contents = result.get("content")
            if not isinstance(contents, list) or not contents:
                raise ValueError("TypeScript tool error lacks content")
            texts = [item.get("text") for item in contents if isinstance(item, dict)]
            if len(texts) != 1 or not isinstance(texts[0], str) or not texts[0]:
                raise ValueError("TypeScript tool error text is invalid")
            key = (path.name, message.get("id"))
            lookup[key]["error"] = texts[0]
            error_shapes.append({"source": path.name, "id": message.get("id"), "shape": "tool_result_isError", "message": texts[0]})
    wire["typescript_error_shapes"] = error_shapes
    wire["jsonrpc_errors"] = jsonrpc_errors
    return wire


def typescript_predicate(case_id: str, db: dict[str, Any], wire: dict[str, Any], exit_codes: list[int]) -> None:
    predicate(case_id, db, wire, exit_codes)
    calls = {(call["source"], call["id"]): call for call in wire["calls"]}
    replies = {(reply["source"], reply["id"]): reply for reply in wire["replies"]}
    statuses = [
        replies[(call["source"], call["id"])]["structured"]
        for call in wire["calls"]
        if call["tool"] == "get_operation_status"
    ]
    if case_id == "02":
        assert len(statuses) == 1
        assert statuses[0]["state"] == "unknown" and statuses[0]["matchingIds"] == []
        assert statuses[0]["authoritative"] is True and statuses[0]["freshWriteAuthorized"] is False
    if case_id == "06":
        assert len(statuses) == 1
        assert statuses[0]["principal"] == "bob" and statuses[0]["state"] == "unknown"
        assert statuses[0]["matchingIds"] == [] and statuses[0]["freshWriteAuthorized"] is False
    if case_id == "12":
        assert len(statuses) == 1
        assert statuses[0]["state"] == "partial" and statuses[0]["matchingIds"] == [db["issues"][0]["id"]]
        assert statuses[0]["authoritative"] is True and statuses[0]["freshWriteAuthorized"] is False
    if case_id in {"04", "05", "06", "07", "10", "11"}:
        assert wire["typescript_error_shapes"], case_id
        assert all(calls[(item["source"], item["id"])]["tool"] == "create_guarded_issue" for item in wire["typescript_error_shapes"])
    if case_id in {"05", "06", "10"}:
        sdk = [item for item in wire["jsonrpc_errors"] if item["code"] == -32602 and "requestState" in item["message"]]
        assert sdk, case_id


def report(records: list[dict[str, Any]], source_head: str) -> str:
    lines = [
        "# TypeScript v2 guarded stdio matrix", "",
        f"Source commit: `{source_head}`. Frozen additive protocol: `5af1fb030f9dae00b4ed336f0bd99237b23d9b05`.",
        "Same Python SQLite bridge; TypeScript SDK wire and state handling are exercised directly.", "",
        "| Case | Expected classification | Status | SQLite issues | Wire replies |", "|---|---|---|---:|---:|",
    ]
    for record in records:
        db = record.get("independent_db") or {}
        wire = record.get("independent_wire") or {}
        lines.append(f"| {record['case_id']} | {record['expected']} | {record['status']} | {len(db.get('issues', []))} | {len(wire.get('replies', []))} |")
    lines.extend(["", "Derived from `results.jsonl`; verify with `python -m scripts.run_typescript_guarded_matrix --verify ATTEMPT_DIR`.", ""])
    return "\n".join(lines)


def verify(attempt: Path) -> dict[str, int]:
    inventory = json.loads(INVENTORY.read_text())
    expected = inventory["expected"]
    records = [json.loads(line) for line in (attempt / "results.jsonl").read_text().splitlines()]
    assert len(records) == len(expected) == 12
    assert {record["case_id"] for record in records} == set(expected)
    provenance = json.loads((attempt / "provenance.json").read_text())
    assert provenance["source_hashes"] == {relative(path): digest(path) for path in SOURCE}
    assert provenance["frozen_protocol_commit"] == "5af1fb030f9dae00b4ed336f0bd99237b23d9b05"
    assert provenance["python_source_commit"] == "3db5a1d551c0000c1288adb71cbf22bab2816c2c"
    assert (attempt / "MATRIX.md").read_text() == report(records, provenance["source_head"])
    for record in records:
        case_id = record["case_id"]
        assert record["expected"] == expected[case_id]
        assert record["status"] == "pass" and record["pytest_exit_code"] == 0, case_id
        assert record["source_hashes"] == provenance["source_hashes"]
        for name, expected_hash in record["artifact_hashes"].items():
            assert digest(ROOT / name) == expected_hash, name
        case_dir = attempt / f"case-{case_id}"
        db = db_facts(case_dir / "store.sqlite3")
        transcripts = sorted(case_dir.glob("*.transcript.log"))
        assert transcripts
        wire = ts_wire_facts(transcripts)
        assert record["independent_db"] == db
        assert record["independent_wire"] == wire
        typescript_predicate(case_id, db, wire, record["process_exit_codes"])
    return {"requested": len(expected), "executed": len(records), "passed": len(records)}


def run(node_modules: Path) -> Path:
    if sys.flags.optimize:
        raise RuntimeError("normal Python assertions are required")
    status = subprocess.check_output(["git", "-c", "core.fsmonitor=false", "status", "--porcelain", "--untracked-files=all"], cwd=ROOT, text=True).strip()
    if status:
        raise RuntimeError("canonical TypeScript matrix requires clean committed source")
    inventory = json.loads(INVENTORY.read_text())
    expected = inventory["expected"]
    assert list(expected) == inventory["case_ids"]
    packages = sdk_packages(node_modules)
    source_head = subprocess.check_output(["git", "-c", "core.fsmonitor=false", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    attempt = DOC / "raw" / f"attempt-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{time.time_ns()}"
    attempt.mkdir(parents=True, exist_ok=False)
    source_hashes = {relative(path): digest(path) for path in SOURCE}
    provenance = {
        "source_head": source_head, "source_hashes": source_hashes,
        "frozen_protocol_commit": "5af1fb030f9dae00b4ed336f0bd99237b23d9b05",
        "python_source_commit": "3db5a1d551c0000c1288adb71cbf22bab2816c2c",
        "python_attempt_summary_sha256": digest(PYTHON_ATTEMPT / "SUMMARY.json"),
        "sdk_packages": packages, "protocol_version": "2026-07-28",
        "environment_allowlist_names": [*BASE_NAMES, "PYTHONPATH", "TS_V2_NODE_MODULES", "NODE_PATH", "WIRE_SERVER_DB", "WIRE_BACKEND_ID", "WIRE_PRINCIPAL", "WIRE_CLOCK_EPOCH", "WIRE_AUTHORITY_TTL", "WIRE_REPLAY_RETENTION_TTL", "WIRE_REQUEST_STATE_TTL", "WIRE_STATE_KEY_HEX", "WIRE_FINGERPRINT_KEY_HEX", "WIRE_FAULT", "MATRIX_ARTIFACT_DIR", "MATRIX_EVIDENCE_JSONL"],
        "environment_values_recorded": False,
        "command_template": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "typescript_v2_tests/test_typescript_guarded_matrix.py::test_guarded_ts_case_XX"],
    }
    (attempt / "provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    results_file = attempt / "results.jsonl"
    for case_id, classification in expected.items():
        evidence = attempt / f"case-{case_id}.test-record.jsonl"
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"typescript_v2_tests/test_typescript_guarded_matrix.py::test_guarded_ts_case_{case_id}"]
        env = {name: os.environ[name] for name in BASE_NAMES if name in os.environ}
        env.update({"PYTHONPATH": os.pathsep.join((str(ROOT), str(ROOT / "src"))), "TS_V2_NODE_MODULES": str(node_modules), "MATRIX_ARTIFACT_DIR": str(attempt), "MATRIX_EVIDENCE_JSONL": str(evidence)})
        try:
            completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45, check=False)
            code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            code = 124
            stdout = exc.stdout.decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else exc.stdout or ""
            stderr = exc.stderr.decode("utf-8", "replace") if isinstance(exc.stderr, bytes) else exc.stderr or ""
            stderr += "\nCASE_TIMEOUT 45 seconds\n"
        (attempt / f"case-{case_id}.pytest.stdout.log").write_text(stdout)
        (attempt / f"case-{case_id}.pytest.stderr.log").write_text(stderr)
        record: dict[str, Any] = {"case_id": case_id, "expected": classification, "status": "machinery_error", "pytest_exit_code": code, "source_hashes": source_hashes, "process_exit_codes": [], "independent_db": None, "independent_wire": None, "artifact_hashes": {}, "command": ["python", *command[1:]]}
        try:
            emitted = [json.loads(line) for line in evidence.read_text().splitlines()]
            assert len(emitted) == 1 and emitted[0]["case_id"] == case_id
            record["process_exit_codes"] = emitted[0]["process_exit_codes"]
            case_dir = attempt / f"case-{case_id}"
            record["independent_db"] = db_facts(case_dir / "store.sqlite3")
            record["independent_wire"] = ts_wire_facts(sorted(case_dir.glob("*.transcript.log")))
            typescript_predicate(case_id, record["independent_db"], record["independent_wire"], record["process_exit_codes"])
            assert code == 0
            record["status"] = "pass"
        except Exception as exc:  # noqa: BLE001 - retain every failed case
            record["status"] = "fail" if code == 0 else "machinery_error"
            record["verification_error"] = f"{type(exc).__name__}: {exc}"
        case_dir = attempt / f"case-{case_id}"
        artifacts = sorted(case_dir.glob("*")) if case_dir.exists() else []
        artifacts += [attempt / f"case-{case_id}.pytest.stdout.log", attempt / f"case-{case_id}.pytest.stderr.log"]
        if evidence.exists():
            artifacts.append(evidence)
        record["artifact_hashes"] = {relative(path): digest(path) for path in artifacts if path.is_file()}
        with results_file.open("a") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    records = [json.loads(line) for line in results_file.read_text().splitlines()]
    (attempt / "MATRIX.md").write_text(report(records, source_head))
    try:
        summary = verify(attempt)
    except Exception as exc:  # noqa: BLE001 - retain failed attempt and all cells
        summary = {"requested": len(expected), "executed": len(records), "passed": sum(record["status"] == "pass" for record in records), "verification_error": f"{type(exc).__name__}: {exc}"}
    (attempt / "SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if "verification_error" in summary:
        raise RuntimeError(f"TypeScript matrix failed; retained {relative(attempt)}: {summary['verification_error']}")
    return attempt


def main() -> None:
    if sys.flags.optimize:
        raise RuntimeError("normal Python assertions are required")
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--node-modules", type=Path)
    group.add_argument("--verify", type=Path)
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.verify.resolve()), sort_keys=True))
    else:
        print(relative(run(args.node_modules.resolve())))


if __name__ == "__main__":
    main()
