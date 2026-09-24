"""Falsifiers for the retained matrix verifier."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.run_completion_matrix import predicate, verify, wire_facts


def test_missing_case_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "results.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(AssertionError):
        verify(tmp_path)


def test_transcript_tamper_fails_parser(tmp_path: Path) -> None:
    transcript = tmp_path / "wire.transcript.log"
    transcript.write_text("> not-json\n", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        wire_facts([transcript])


def test_wrong_replay_flag_fails_independent_predicate() -> None:
    db = {
        "issues": [{"id": 1, "title": "guarded-01", "body": "alpha"}],
        "operations": [{"operation_id": "case-01", "principal": "alice", "backend": "sqlite:guarded-matrix", "state": "applied", "effect_id": 1}],
        "watchers": [], "compensations": [], "events": [],
    }
    wire = {
        "request_protocol_versions": ["2026-07-28"],
        "calls": [
            {"source": "wire", "id": 1, "tool": "create_guarded_issue", "continuation": True, "state_present": True},
            {"source": "wire", "id": 2, "tool": "create_guarded_issue", "continuation": True, "state_present": True},
        ],
        "replies": [
            {"source": "wire", "id": 1, "error": None, "structured": {"replayed": False, "result": "created 1"}},
            {"source": "wire", "id": 2, "error": None, "structured": {"replayed": False, "result": "created 1"}},
        ],
    }
    with pytest.raises(AssertionError):
        predicate("01", db, wire, [0])
