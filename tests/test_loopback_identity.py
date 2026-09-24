"""Additive per-request test identity over pinned SDK Streamable HTTP."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from tests.http_client import free_port, request, start_server, stop_server
from tests.test_guarded_wire_matrix import _args


def test_two_authenticated_loopback_contexts_are_isolated(tmp_path: Path) -> None:
    db = tmp_path / "identity.sqlite3"
    port = free_port()
    server = start_server(db, port)
    args = _args("test-auth")
    try:
        status, first = request(port, "create_guarded_issue", args, 10)
        assert status == 200 and first["result"]["resultType"] == "input_required"
        state = first["result"]["requestState"]
        status, applied = request(port, "create_guarded_issue", args, 11, state=state, body="alpha")
        assert status == 200 and applied["result"]["structuredContent"]["result"] == "created 1"

        status, alice = request(
            port, "get_operation_status", {"operation_id": args["operation_id"]}, 12
        )
        assert status == 200
        assert alice["result"]["structuredContent"]["storedResult"] == "created 1"
        status, bob = request(
            port,
            "get_operation_status",
            {"operation_id": args["operation_id"]},
            13,
            principal="bob",
        )
        assert status == 200
        assert bob["result"]["structuredContent"]["state"] == "unknown"
        assert bob["result"]["structuredContent"]["storedResult"] is None
        status, stolen = request(
            port, "create_guarded_issue", args, 14, principal="bob", state=state, body="alpha"
        )
        assert status >= 400 or "error" in stolen
        status, bob_first = request(port, "create_guarded_issue", args, 16, principal="bob")
        assert status == 200 and bob_first["result"]["resultType"] == "input_required"
        status, bob_denied = request(
            port,
            "create_guarded_issue",
            args,
            17,
            principal="bob",
            state=bob_first["result"]["requestState"],
            body="alpha",
        )
        assert status >= 400 or "error" in bob_denied
        status, denied = request(
            port,
            "get_operation_status",
            {"operation_id": args["operation_id"]},
            15,
            principal="invalid",
        )
        assert status == 401 and "result" not in denied
    finally:
        stop_server(server)
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        assert conn.execute("SELECT count(*) FROM issues").fetchone()[0] == 1
        assert conn.execute("SELECT principal FROM operations").fetchone()[0] == "alice"
