"""Run additive fault cells and retain wire, SQLite and exact environment facts."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import signal
import sqlite3
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CELLS = (
    "tests/test_fault_lab.py",
    "typescript_v2_tests/test_fault_lab_typescript.py",
    "tests/test_unsafe_control.py",
)
EXPECTED_CASES = (
    "test_precommit_hard_exit_rolls_back_both_rows[exit-after-ledger-insert-71]",
    "test_precommit_hard_exit_rolls_back_both_rows[exit-after-issue-insert-72]",
    "test_sqlite_busy_fails_before_dispatch_and_preserves_identity",
    "test_exception_after_issue_insert_rolls_back_both_rows",
    "test_bridge_precommit_exit_has_no_durable_effect[exit-after-ledger-insert-71]",
    "test_bridge_precommit_exit_has_no_durable_effect[exit-after-issue-insert-72]",
    "test_unsafe_new_identity_retry_duplicates_the_effect",
)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _database(path: Path) -> dict[str, int | str]:
    uri = f"file:{path}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        return {"readback_error": f"{type(exc).__name__}: {exc}"}
    try:
        try:
            return {
                "issues": int(connection.execute("SELECT count(*) FROM issues").fetchone()[0]),
                "operations": int(
                    connection.execute("SELECT count(*) FROM operations").fetchone()[0]
                ),
            }
        except sqlite3.Error as exc:
            return {"readback_error": f"{type(exc).__name__}: {exc}"}
    finally:
        connection.close()


def _source_state() -> dict[str, str | bool]:
    return {
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "dirty": bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT)),
    }


def _invoke(command: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=120)
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired as final:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
                stdout = _partial_text(final.stdout) or _partial_text(exc.stdout)
                stderr = _partial_text(final.stderr) or _partial_text(exc.stderr)
        raise subprocess.TimeoutExpired(
            command,
            120,
            output=stdout or _partial_text(exc.stdout),
            stderr=stderr or _partial_text(exc.stderr),
        ) from exc
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _partial_text(value: str | bytes | None) -> str:
    return value.decode("utf-8", "replace") if isinstance(value, bytes) else value or ""


def _observed_cases(junit: Path) -> tuple[dict[str, str], str | None]:
    try:
        root = ET.parse(junit).getroot()
        suite = root if root.tag == "testsuite" else root.find("testsuite")
        if suite is None:
            raise ValueError("missing JUnit suite")
        seen: dict[str, str] = {}
        for item in suite.findall("testcase"):
            name = item.attrib.get("name", "")
            if name not in EXPECTED_CASES or name in seen:
                raise ValueError(f"unexpected or duplicate JUnit case: {name}")
            seen[name] = (
                "failed"
                if item.find("failure") is not None or item.find("error") is not None
                else "skipped"
                if item.find("skipped") is not None
                else "passed"
            )
        return seen, None
    except (OSError, ValueError, ET.ParseError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def run(output: Path, node_modules: Path) -> dict[str, object]:
    output = output.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("output must be outside source tree")
    node_modules = node_modules.resolve(strict=True)
    if not (node_modules / "@modelcontextprotocol/server/package.json").is_file():
        raise ValueError("TypeScript v2 dependencies are not installed")
    before = _source_state()
    package_versions = {
        package: json.loads((node_modules / package / "package.json").read_text())["version"]
        for package in ("@modelcontextprotocol/core", "@modelcontextprotocol/server", "zod")
    }
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env["TS_V2_NODE_MODULES"] = str(node_modules)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "-W",
        "error::ResourceWarning",
        "--basetemp",
        str(output / "pytest"),
        "--junitxml",
        str(output / "junit.xml"),
        *CELLS,
    ]
    timed_out = False
    try:
        completed = _invoke(command, env)
        stdout, stderr = completed.stdout, completed.stderr
        exit_code: int | None = completed.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stdout, stderr = _partial_text(exc.stdout), _partial_text(exc.stderr)
        exit_code = None
    (output / "pytest.stdout.log").write_text(_partial_text(stdout), encoding="utf-8")
    (output / "pytest.stderr.log").write_text(_partial_text(stderr), encoding="utf-8")
    observed, junit_error = _observed_cases(output / "junit.xml")
    missing_status = "unknown_after_timeout" if timed_out else "not_reported"
    cases = [
        {"name": name, "status": observed.get(name, missing_status)} for name in EXPECTED_CASES
    ]
    databases = {
        path.relative_to(output).as_posix(): _database(path)
        for path in sorted((output / "pytest").rglob("*.sqlite3"))
    }
    artifacts = {
        path.relative_to(output).as_posix(): _digest(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "RESULT.json"
    }
    after = _source_state()
    source_changed = before != after
    report: dict[str, object] = {
        "protocol": "fault-lab-v1-exposed-regression",
        "source_head": before["head"],
        "source_before": before,
        "source_after": after,
        "source_changed": source_changed,
        "source_dirty": before["dirty"] or after["dirty"],
        "python": sys.version.split()[0],
        "node": subprocess.check_output(["node", "--version"], text=True).strip(),
        "mcp_python": importlib.metadata.version("mcp"),
        "typescript_v2_packages": package_versions,
        "requested": len(EXPECTED_CASES),
        "executed": len(observed),
        "passed": sum(case["status"] == "passed" for case in cases),
        "failed": sum(case["status"] == "failed" for case in cases),
        "skipped": sum(case["status"] == "skipped" for case in cases),
        "not_reported": len(EXPECTED_CASES) - len(observed),
        "pytest_exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_seconds": 120,
        "junit_error": junit_error,
        "machinery_failure": timed_out
        or junit_error is not None
        or (exit_code not in (0, None) and not any(case["status"] == "failed" for case in cases)),
        "cases": cases,
        "physical_readback": databases,
        "artifact_sha256": artifacts,
        "unsafe_control_detected": any(
            case["name"] == "test_unsafe_new_identity_retry_duplicates_the_effect"
            and case["status"] == "passed"
            for case in cases
        ),
        "claim_limit": "same-author fixtures over one Python SQLite engine; TypeScript v2 fault cells use a Python bridge",
    }
    (output / "RESULT.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if (
        exit_code != 0
        or timed_out
        or junit_error
        or len(observed) != len(EXPECTED_CASES)
        or report["passed"] != len(EXPECTED_CASES)
        or not report["unsafe_control_detected"]
        or any("readback_error" in facts for facts in databases.values())
        or report["source_dirty"]
        or source_changed
    ):
        raise ValueError(f"fault lab incomplete; retained attempt: {output}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--node-modules", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.output_dir, args.node_modules)
        print(
            json.dumps(
                {
                    key: report[key]
                    for key in (
                        "source_head",
                        "python",
                        "node",
                        "requested",
                        "executed",
                        "passed",
                        "failed",
                        "unsafe_control_detected",
                    )
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError, subprocess.TimeoutExpired, ET.ParseError) as exc:
        parser.exit(1, f"fault lab failed: {exc}\n")


if __name__ == "__main__":
    main()
