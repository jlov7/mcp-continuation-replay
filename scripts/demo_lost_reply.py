"""Run frozen guarded case 03 and summarize its real wire and SQLite readback."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.run_completion_matrix import db_facts, wire_facts

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="new directory outside source tree"
    )
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("output must be outside the source checkout")
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env["MATRIX_ARTIFACT_DIR"] = str(output)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/test_guarded_wire_matrix.py::test_guarded_case_03_lost_reply_explicit_replay_is_one_effect",
    ]
    completed = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=45, check=False
    )
    if completed.returncode:
        parser.exit(completed.returncode, completed.stdout + completed.stderr)
    case = output / "case-03"
    db = db_facts(case / "store.sqlite3")
    wire = wire_facts([case / "crash.transcript.log", case / "restart.transcript.log"])
    calls = wire["calls"]
    replies = wire["replies"]
    if not any(item["result_type"] == "input_required" for item in replies):
        raise SystemExit("missing input_required wire round")
    if not any(item["source"] == "crash.transcript.log" and item["continuation"] for item in calls):
        raise SystemExit("missing lost-reply continuation")
    if any(item["source"] == "crash.transcript.log" and item["id"] == 11 for item in replies):
        raise SystemExit("lost reply unexpectedly present")
    status = [
        item["structured"]
        for item in replies
        if isinstance(item["structured"], dict) and item["structured"].get("authoritative") is True
    ]
    replay = [
        item["structured"]
        for item in replies
        if isinstance(item["structured"], dict) and item["structured"].get("replayed") is True
    ]
    if len(status) != 1 or len(replay) != 1 or len(db["issues"]) != 1 or len(db["operations"]) != 1:
        raise SystemExit("wire/physical readback mismatch")
    result = {
        "case": "03: guarded lost reply and recovery",
        "input_required": True,
        "transport_after_commit": "unknown; no reply",
        "status": {
            key: status[0][key]
            for key in (
                "operationId",
                "principal",
                "backend",
                "state",
                "authoritative",
                "freshWriteAuthorized",
                "matchingIds",
            )
        },
        "replay": {key: replay[0][key] for key in ("operationId", "effectId", "replayed", "state")},
        "physical_issue_rows": len(db["issues"]),
        "physical_operation_rows": len(db["operations"]),
        "operation_id": db["operations"][0]["operation_id"],
        "raw_artifacts": str(case),
    }
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
