"""Machinery tests.

These validate the *instrument*, not any protocol behaviour. A passing test here
means the harness can detect a duplicate effect at all. Without this, a later
"no duplicate observed" result would be indistinguishable from a broken detector.

Per the brief: fixture tests validate machinery; they are not empirical evidence.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier

import pytest

from reference.backend import (
    IssueStore,
    OperationAuthorityExpired,
    OperationConflict,
    OperationIdentity,
    OperationRetentionExpired,
    WatcherInsertFailed,
)
from reference.consumer import ContinuationConsumer
from reference.readback import ReadBack
from reference.wire_recovery import observation_from_wire


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("operationId", 123),
        ("principal", None),
        ("backend", ""),
        ("authoritative", False),
        ("freshWriteAuthorized", True),
        ("state", "nope"),
        ("matchingIds", []),
        ("matchingIds", [1, 1]),
        ("matchingIds", [True]),
        ("matchingIds", [0]),
        ("observedAt", "2026-09-22T12:00:00"),
        ("scope", ""),
    ],
)
def test_wire_recovery_rejects_malformed_authoritative_status(field: str, bad: object) -> None:
    identity = OperationIdentity("op", "alice", "backend")
    status: dict[str, object] = {
        "operationId": "op",
        "principal": "alice",
        "backend": "backend",
        "authoritative": True,
        "freshWriteAuthorized": False,
        "state": "applied",
        "matchingIds": [1],
        "observedAt": "2026-09-22T12:00:00+00:00",
        "scope": "exact operation",
        "detail": "one issue",
    }
    status[field] = bad
    with pytest.raises(ValueError):
        observation_from_wire(status, expected_identity=identity)


def test_readback_does_not_call_orphaned_ledger_applied() -> None:
    store = IssueStore(":memory:")
    identity = OperationIdentity("orphan", "alice", store.backend_id)
    try:
        applied = store.apply_issue_once(identity, request_fingerprint="fingerprint", title="t", body="b")
        assert ReadBack(store, principal="alice").reconcile_operation(identity).state == "applied"
        store._conn.execute("PRAGMA foreign_keys = OFF")
        store._conn.execute("DELETE FROM issues WHERE id = ?", (applied.effect_id,))
        store._conn.commit()
        observed = ReadBack(store, principal="alice").reconcile_operation(identity)
        assert observed.state == "unknown" and observed.matching_ids == ()
    finally:
        store.close()


def test_store_is_deliberately_not_idempotent() -> None:
    """Two identical creates must produce two rows, or the detector is blind."""
    store = IssueStore(":memory:")
    try:
        first = store.create_issue("spec", body="alpha")
        second = store.create_issue("spec", body="alpha")
        assert first != second
        assert store.count() == 2
    finally:
        store.close()


def test_readback_distinguishes_not_applied_from_applied() -> None:
    store = IssueStore(":memory:")
    try:
        rb = ReadBack(store)
        assert rb.observe_by_title("absent", operation_id="absent").state == "not_applied"
        assert rb.observe_by_title("absent", operation_id="absent").effects == 0

        store.create_issue("present", body="alpha")
        assert rb.observe_by_title("present", operation_id="present").state == "applied"
        assert rb.observe_by_title("present", operation_id="present").effects == 1

        # Two rows under one title must be visible as two effects, not one.
        store.create_issue("present", body="alpha")
        assert rb.observe_by_title("present", operation_id="present").effects == 2
    finally:
        store.close()


def test_readback_is_scoped_by_body_not_just_title() -> None:
    """The body is the discriminator for changed-input-responses experiments."""
    store = IssueStore(":memory:")
    try:
        rb = ReadBack(store)
        store.create_issue("spec", body="alpha")
        assert rb.observe_by_body("alpha", operation_id="body-probe").effects == 1
        assert rb.observe_by_body("beta", operation_id="body-probe").effects == 0
    finally:
        store.close()


def test_reset_clears_effect_visibility() -> None:
    store = IssueStore(":memory:")
    try:
        store.create_issue("spec", body="alpha")
        store.reset()
        assert store.count() == 0
    finally:
        store.close()


def test_partial_watcher_effect_is_visible_to_readback() -> None:
    """The case-12 instrument: a committed issue with a failed sub-effect reads back as partial."""
    store = IssueStore(":memory:")
    try:
        rb = ReadBack(store)
        try:
            store.create_issue_with_watcher("p", "alpha", "w@test", fail_watcher=True)
            raise AssertionError("WatcherInsertFailed was expected")
        except WatcherInsertFailed:
            pass
        observed = rb.observe_issue_with_watcher("p", "w@test", operation_id="partial")
        assert observed.state == "partial"
        assert observed.effects == 1
    finally:
        store.close()


def test_full_watcher_effect_reads_back_applied() -> None:
    store = IssueStore(":memory:")
    try:
        rb = ReadBack(store)
        issue_id = store.create_issue_with_watcher("a", "alpha", "w@test")
        assert (
            rb.observe_issue_with_watcher("a", "w@test", operation_id="watcher").state == "applied"
        )
        assert (
            rb.observe_issue_with_watcher("a", "other@test", operation_id="watcher").state
            == "partial"
        )
        assert (
            rb.observe_issue_with_watcher("missing", "w@test", operation_id="watcher").state
            == "not_applied"
        )
        assert store.watchers_for(issue_id)[0].name == "w@test"
    finally:
        store.close()


def test_compensation_keeps_separate_identity_and_never_rewrites() -> None:
    store = IssueStore(":memory:")
    try:
        rb = ReadBack(store)
        issue_id = store.create_issue("c", body="alpha")
        comp_id = store.record_compensation(issue_id, kind="manual", outcome="failed")
        comps = rb.compensations_for(issue_id)
        assert len(comps) == 1
        assert comps[0].id == comp_id
        assert comps[0].outcome == "failed"
        original = store.get_issue(issue_id)
        assert original is not None and original.body == "alpha"
    finally:
        store.close()


def test_mediated_apply_replays_result_and_conflicts_before_dispatch() -> None:
    store = IssueStore(":memory:", backend_id="sqlite:mediated")
    identity = OperationIdentity("op-1", "alice", "sqlite:mediated")
    try:
        first = store.apply_issue_once(
            identity, request_fingerprint="fp-alpha", title="spec", body="alpha"
        )
        replay = store.apply_issue_once(
            identity, request_fingerprint="fp-alpha", title="spec", body="alpha"
        )
        assert first.replayed is False
        assert replay.replayed is True
        assert replay.effect_id == first.effect_id
        assert replay.result == first.result
        assert store.count() == 1

        with pytest.raises(OperationConflict, match="different principal, backend, or request"):
            store.apply_issue_once(
                identity, request_fingerprint="fp-beta", title="spec", body="beta"
            )
        assert store.count() == 1
    finally:
        store.close()


def test_guarded_multistep_success_executes_watcher_and_skips_compensation() -> None:
    store = IssueStore(":memory:", backend_id="sqlite:steps")
    identity = OperationIdentity("op-steps", "alice", "sqlite:steps")
    calls: list[str] = []

    def add_watcher(conn: sqlite3.Connection, issue_id: int, watcher: str) -> None:
        calls.append("watcher")
        conn.execute("INSERT INTO watchers (issue_id, name) VALUES (?, ?)", (issue_id, watcher))

    def compensate(_conn: sqlite3.Connection, _issue_id: int) -> None:
        calls.append("compensation")

    try:
        result = store.apply_partial_issue_once(
            identity,
            request_fingerprint="fp-steps",
            title="steps",
            body="alpha",
            watcher="w@test",
            issued_at=100,
            authority_expires_at=200,
            replay_expires_at=300,
            now_epoch=100,
            watcher_operation=add_watcher,
            compensation_operation=compensate,
        )
        assert result.state == "applied"
        assert calls == ["watcher"]
        assert [watcher.name for watcher in store.watchers_for(result.effect_id)] == ["w@test"]
        assert [(event.step, event.outcome) for event in store.operation_events("op-steps")] == [
            ("watcher", "attempted"),
            ("watcher", "succeeded"),
        ]
    finally:
        store.close()


def test_bounded_operation_rejects_exact_deadlines_and_missing_replay_clock() -> None:
    authority_store = IssueStore(":memory:", backend_id="sqlite:authority-deadline")
    authority_identity = OperationIdentity("op", "alice", "sqlite:authority-deadline")
    try:
        with pytest.raises(OperationAuthorityExpired):
            authority_store.apply_issue_once(
                authority_identity,
                request_fingerprint="fp",
                title="deadline",
                body="alpha",
                issued_at=100,
                authority_expires_at=110,
                replay_expires_at=120,
                now_epoch=110,
            )
        assert authority_store.count() == 0
    finally:
        authority_store.close()

    retention_store = IssueStore(":memory:", backend_id="sqlite:retention-deadline")
    retention_identity = OperationIdentity("op", "alice", "sqlite:retention-deadline")
    try:
        retention_store.apply_issue_once(
            retention_identity,
            request_fingerprint="fp",
            title="deadline",
            body="alpha",
            issued_at=100,
            authority_expires_at=130,
            replay_expires_at=120,
            now_epoch=100,
        )
        with pytest.raises(OperationRetentionExpired):
            retention_store.apply_issue_once(
                retention_identity,
                request_fingerprint="fp",
                title="deadline",
                body="alpha",
                now_epoch=120,
            )
        with pytest.raises(ValueError, match="now_epoch"):
            retention_store.apply_issue_once(
                retention_identity,
                request_fingerprint="fp",
                title="deadline",
                body="alpha",
            )
        assert retention_store.count() == 1
    finally:
        retention_store.close()


def test_reconciliation_requires_exact_authorized_identity() -> None:
    store = IssueStore(":memory:", backend_id="sqlite:reconcile")
    identity = OperationIdentity("op-1", "alice", "sqlite:reconcile")
    try:
        rb = ReadBack(store, principal="alice")
        missing = rb.reconcile_operation(identity)
        assert missing.state == "unknown"
        assert missing.authoritative is True

        store.apply_issue_once(identity, request_fingerprint="fp-alpha", title="spec", body="alpha")
        consumer = ContinuationConsumer(identity)
        settled = consumer.reconcile(rb.reconcile_operation)
        assert settled.effect == "applied"
        assert settled.observation is not None
        assert settled.observation.identity == identity
        assert settled.observation.observed_at.endswith("+00:00")

        with pytest.raises(ValueError, match="principal"):
            ReadBack(store, principal="bob").reconcile_operation(identity)
        with pytest.raises(ValueError, match="backend"):
            rb.reconcile_operation(OperationIdentity("op-1", "alice", "sqlite:other"))
    finally:
        store.close()


def test_file_store_persists_and_enforces_backend_binding(tmp_path) -> None:
    path = tmp_path / "bound.db"
    store = IssueStore(str(path), backend_id="sqlite:bound")
    store.close()
    reopened = IssueStore(str(path), backend_id="sqlite:bound")
    reopened.close()
    with pytest.raises(ValueError, match="bound to backend_id"):
        IssueStore(str(path), backend_id="sqlite:other")


def test_simultaneous_first_use_serializes_schema_and_binding(tmp_path) -> None:
    path = tmp_path / "fresh.db"
    barrier = Barrier(2)

    def open_store() -> None:
        barrier.wait()
        store = IssueStore(str(path), backend_id="sqlite:shared")
        try:
            assert store.count() == 0
        finally:
            store.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(open_store) for _ in range(2)]
        for future in futures:
            future.result(timeout=10)
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT value FROM store_metadata WHERE key='backend_id'").fetchone() == ("sqlite:shared",)
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='operations'").fetchone() == ("operations",)


def test_simultaneous_conflicting_backend_ids_rejects_loser(tmp_path) -> None:
    path = tmp_path / "conflicting.db"
    barrier = Barrier(2)

    def open_store(backend_id: str) -> tuple[str, str]:
        barrier.wait()
        try:
            store = IssueStore(str(path), backend_id=backend_id)
        except ValueError as exc:
            assert "bound to backend_id" in str(exc)
            return ("rejected", backend_id)
        else:
            store.close()
            return ("accepted", backend_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(open_store, backend_id) for backend_id in ("sqlite:a", "sqlite:b")]
        outcomes = [future.result(timeout=10) for future in futures]
    assert {outcome for outcome, _ in outcomes} == {"accepted", "rejected"}
    accepted = next(backend_id for outcome, backend_id in outcomes if outcome == "accepted")
    with closing(sqlite3.connect(path)) as conn:
        assert conn.execute("SELECT value FROM store_metadata WHERE key='backend_id'").fetchone() == (accepted,)
    reopened = IssueStore(str(path), backend_id=accepted)
    reopened.close()


def test_reset_clears_dependent_rows_without_foreign_key_failure() -> None:
    store = IssueStore(":memory:")
    try:
        issue_id = store.create_issue_with_watcher("spec", "alpha", "w@test")
        store.record_compensation(issue_id, "manual", "failed")
        store.reset()
        assert store.count() == 0
        assert store.watchers_for(issue_id) == []
        assert store.compensations_for(issue_id) == []
    except sqlite3.IntegrityError as exc:  # explicit diagnostic if delete ordering regresses
        raise AssertionError("reset violated dependent-row ordering") from exc
    finally:
        store.close()
