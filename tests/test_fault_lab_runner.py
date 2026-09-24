"""A lab timeout must leave a complete failure receipt and partial logs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import run_fault_lab


def test_timeout_retains_unknown_cells_and_partial_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node_modules = tmp_path / "node_modules"
    for package in ("@modelcontextprotocol/core", "@modelcontextprotocol/server", "zod"):
        path = node_modules / package / "package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"version":"2.0.0"}', encoding="utf-8")
    monkeypatch.setattr(run_fault_lab, "_source_state", lambda: {"head": "a" * 40, "dirty": False})

    def time_out(_command: list[str], _env: dict[str, str]) -> None:
        raise subprocess.TimeoutExpired(
            "pytest", 120, output=b"partial stdout", stderr=b"partial stderr"
        )

    monkeypatch.setattr(run_fault_lab, "_invoke", time_out)
    output = tmp_path / "attempt"
    with pytest.raises(ValueError, match="fault lab incomplete"):
        run_fault_lab.run(output, node_modules)
    report = json.loads((output / "RESULT.json").read_text(encoding="utf-8"))
    assert report["requested"] == 7 and report["executed"] == 0
    assert report["timed_out"] is True and report["machinery_failure"] is True
    assert all(case["status"] == "unknown_after_timeout" for case in report["cases"])
    assert (output / "pytest.stdout.log").read_text() == "partial stdout"
    assert (output / "pytest.stderr.log").read_text() == "partial stderr"
    assert report["artifact_sha256"]


def test_missing_junit_retains_machinery_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node_modules = tmp_path / "node_modules"
    for package in ("@modelcontextprotocol/core", "@modelcontextprotocol/server", "zod"):
        path = node_modules / package / "package.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"version":"2.0.0"}', encoding="utf-8")
    monkeypatch.setattr(run_fault_lab, "_source_state", lambda: {"head": "a" * 40, "dirty": False})
    monkeypatch.setattr(
        run_fault_lab,
        "_invoke",
        lambda _command, _env: subprocess.CompletedProcess("pytest", 1, "stdout", "stderr"),
    )
    output = tmp_path / "attempt"
    with pytest.raises(ValueError, match="fault lab incomplete"):
        run_fault_lab.run(output, node_modules)
    report = json.loads((output / "RESULT.json").read_text(encoding="utf-8"))
    assert report["junit_error"] and report["machinery_failure"]
    assert report["not_reported"] == 7
    assert all(case["status"] == "not_reported" for case in report["cases"])
