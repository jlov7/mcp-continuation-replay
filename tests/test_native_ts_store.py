"""Predeclared native TypeScript store cells with independent SQLite readback."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "adapters" / "typescript" / "src" / "native_store_cli.ts"
BACKEND = "sqlite:native-ts"


def _call(
    db: Path, operation_id: str, *, op: object = "apply", **changes: object
) -> subprocess.CompletedProcess[str]:
    value = {
        "db": str(db),
        "backend": BACKEND,
        "op": op,
        "identity": {"operationId": operation_id, "principal": "alice", "backend": BACKEND},
        "fingerprint": "fp-alpha",
        "title": "native",
        "body": "alpha",
        "now": 100,
        "replayExpiresAt": 200,
        **changes,
    }
    node = os.environ.get("NATIVE_NODE", "node")
    return subprocess.run(
        [node, "--experimental-strip-types", str(CLI)],
        input=json.dumps(value),
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )


def _counts(db: Path) -> tuple[int, int]:
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return (
            conn.execute("SELECT count(*) FROM effects").fetchone()[0],
            conn.execute("SELECT count(*) FROM operations").fetchone()[0],
        )


def _effects(db: Path) -> list[tuple[int, str, str]]:
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        return conn.execute("SELECT id, title, body FROM effects ORDER BY id").fetchall()


def test_native_store_predeclared_cells(tmp_path: Path) -> None:
    db = tmp_path / "native.sqlite3"
    assert json.loads(_call(db, "absent", op="status").stdout)["state"] == "unknown"
    assert _counts(db) == (0, 0)

    lost = _call(db, "lost", dropReply=True)
    assert lost.returncode == 70 and not lost.stdout
    status = json.loads(_call(db, "lost", op="status").stdout)
    assert status == {
        "state": "applied",
        "effectId": 1,
        "storedResult": "created 1",
        "freshWriteAuthorized": False,
    }
    assert _counts(db) == (1, 1)
    replay = json.loads(_call(db, "lost").stdout)
    assert replay["replayed"] is True and _counts(db) == (1, 1)

    conflict = _call(db, "lost", fingerprint="fp-beta")
    assert conflict.returncode == 1 and "operation_conflict" in conflict.stderr
    assert _counts(db) == (1, 1)
    for payload_change in ({"title": "different"}, {"body": "different"}):
        conflict = _call(db, "lost", **payload_change)
        assert conflict.returncode == 1 and "operation_conflict" in conflict.stderr
        assert _counts(db) == (1, 1)
        assert _effects(db) == [(1, "native", "alpha")]
    expiry = _call(db, "lost", now=200)
    assert expiry.returncode == 1 and "operation_retention_expired" in expiry.stderr
    assert _counts(db) == (1, 1)

    node = os.environ.get("NATIVE_NODE", "node")
    holding = tmp_path / "first-holding"
    peer_attempt = tmp_path / "peer-attempt"
    peer_ready = tmp_path / "peer-ready"
    peer_start = tmp_path / "peer-start"
    payload = {
        "db": str(db),
        "backend": BACKEND,
        "op": "apply",
        "identity": {"operationId": "race", "principal": "alice", "backend": BACKEND},
        "fingerprint": "fp-race",
        "title": "race",
        "body": "alpha",
        "now": 100,
        "replayExpiresAt": 200,
    }
    second = subprocess.Popen(
        [node, "--experimental-strip-types", str(CLI)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert second.stdin is not None
    second.stdin.write(
        json.dumps(
            {
                **payload,
                "signalBeforeApplyPath": str(peer_attempt),
                "readyPath": str(peer_ready),
                "startWhenPath": str(peer_start),
            }
        )
    )
    second.stdin.close()
    deadline = time.monotonic() + 8
    while not peer_ready.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert peer_ready.exists() and second.poll() is None
    first = subprocess.Popen(
        [node, "--experimental-strip-types", str(CLI)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert first.stdin is not None
    first.stdin.write(
        json.dumps(
            {
                **payload,
                "holdTransactionPath": str(holding),
                "peerAttemptPath": str(peer_attempt),
            }
        )
    )
    first.stdin.close()
    deadline = time.monotonic() + 8
    while not holding.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert holding.exists() and first.poll() is None
    peer_start.write_text("go")
    procs = [first, second]
    for proc in procs:
        proc.wait(timeout=8)
    results = []
    for proc in procs:
        assert proc.stdout is not None and proc.stderr is not None
        results.append((proc.stdout.read(), proc.stderr.read()))
        proc.stdout.close()
        proc.stderr.close()
    assert all(proc.returncode == 0 for proc in procs), results
    assert sorted(json.loads(output)["replayed"] for output, _ in results) == [False, True]
    assert (holding.read_text(), peer_ready.read_text(), peer_attempt.read_text()) == (
        "holding",
        "ready",
        "attempting",
    )
    assert _counts(db) == (2, 2)

    # Deliberately unsafe new identity is detectable as a second effect.
    unsafe = _call(db, "lost-new-identity")
    assert unsafe.returncode == 0 and _counts(db) == (3, 3)


def test_native_cli_rejects_invalid_operation_and_payload_before_effect(tmp_path: Path) -> None:
    db = tmp_path / "native.sqlite3"
    assert _call(db, "valid").returncode == 0
    original = _effects(db)
    invalid = (
        {"op": "erase"},
        {"title": 7},
        {"body": 7},
        {"fingerprint": 7},
        {"identity": {"operationId": "invalid", "principal": 7, "backend": BACKEND}},
    )
    for change in invalid:
        result = _call(db, "invalid", **change)
        assert result.returncode == 1
        assert "invalid" in result.stderr
        assert _effects(db) == original
        assert _counts(db) == (1, 1)
