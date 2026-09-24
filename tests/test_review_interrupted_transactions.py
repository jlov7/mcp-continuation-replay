"""In-process interruption must not leave a transaction for a later call to commit."""

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from reference.backend import IssueStore, OperationIdentity, OperationInProgress


@pytest.mark.parametrize(
    "error_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit, RuntimeError]
)
@pytest.mark.parametrize("boundary", ["after-ledger-insert", "after-issue-insert"])
def test_precommit_interruption_rolls_back_and_releases_writer(
    tmp_path: Path, error_type: type[BaseException], boundary: str
) -> None:
    path = tmp_path / "issues.sqlite"
    store = IssueStore(str(path), backend_id="review-backend")
    identity = OperationIdentity("interrupted", "test-principal", store.backend_id)
    interruption = error_type("injected interruption")

    def interrupt(step: str) -> None:
        if step == boundary:
            raise interruption

    try:
        with pytest.raises(error_type) as caught:
            store.apply_issue_once(
                identity,
                request_fingerprint="bound-request",
                title="must-not-commit",
                body="synthetic",
                fault_hook=interrupt,
            )
        assert caught.value is interruption
        assert store.operation_count() == 0
        assert store.count() == 0
        # A separate writer must not be blocked by this surviving process.
        with closing(sqlite3.connect(path, timeout=0)) as other:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
        store.create_issue("unrelated")
        assert store.issues_with_title("must-not-commit") == []
        result = store.apply_issue_once(
            identity, request_fingerprint="bound-request", title="must-not-commit", body="synthetic"
        )
        assert not result.replayed
        assert store.operation_count() == 1
        assert store.count() == 2
    finally:
        store.close()


@pytest.mark.parametrize("error_type", [asyncio.CancelledError, KeyboardInterrupt, SystemExit])
@pytest.mark.parametrize("interrupt_during", ["watcher", "compensation"])
def test_partial_interruption_rolls_back_only_uncommitted_subeffect(
    tmp_path: Path, error_type: type[BaseException], interrupt_during: str
) -> None:
    path = tmp_path / "partial.sqlite"
    store = IssueStore(str(path), backend_id="review-backend")
    identity = OperationIdentity("partial", "test-principal", store.backend_id)
    interruption = error_type("injected interruption")

    def watcher(conn: sqlite3.Connection, effect_id: int, name: str) -> None:
        conn.execute("INSERT INTO watchers(issue_id, name) VALUES (?, ?)", (effect_id, name))
        if interrupt_during == "watcher":
            raise interruption
        raise RuntimeError("ordinary watcher failure")

    def compensate(conn: sqlite3.Connection, effect_id: int) -> None:
        conn.execute(
            "INSERT INTO compensations(issue_id, kind, outcome) VALUES (?, ?, ?)",
            (effect_id, "interrupted-compensation", "uncommitted"),
        )
        raise interruption

    try:
        with pytest.raises(error_type) as caught:
            store.apply_partial_issue_once(
                identity,
                request_fingerprint="bound-request",
                title="committed-first-effect",
                body="synthetic",
                watcher="synthetic-watcher",
                issued_at=100,
                authority_expires_at=200,
                replay_expires_at=300,
                now_epoch=150,
                watcher_operation=watcher,
                compensation_operation=compensate,
            )
        assert caught.value is interruption
        record = store.operation_record(identity)
        assert record is not None and record.effect_id is not None
        assert record.state == "in_progress"
        assert store.count() == store.operation_count() == 1
        assert store.watchers_for(record.effect_id) == []
        assert store.compensations_for(record.effect_id) == []
        with closing(sqlite3.connect(path, timeout=0)) as other:
            other.execute("BEGIN IMMEDIATE")
            other.rollback()
        with pytest.raises(OperationInProgress):
            store.apply_issue_once(
                identity,
                request_fingerprint="bound-request",
                title="committed-first-effect",
                body="synthetic",
                now_epoch=150,
            )
        assert store.count() == 1
    finally:
        store.close()
