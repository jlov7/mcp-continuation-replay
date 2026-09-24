"""Predeclared real loopback intermediary drop, delay and strip cells."""

from __future__ import annotations

import base64
import http.client
import json
import os
import socket
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from pathlib import Path

import pytest

from tests.http_client import ROOT, free_port, request, start_server, stop_server
from tests.test_guarded_wire_matrix import _args


def _start_proxy(port: int, upstream: int, mode: str, log: Path) -> subprocess.Popen[bytes]:
    env = {k: v for k, v in os.environ.items() if k in {"PATH", "LANG", "LC_ALL", "TMPDIR"}}
    coverage_enabled = bool(os.environ.get("COVERAGE_PROCESS_CONFIG"))
    if coverage_enabled:
        env["COVERAGE_PROCESS_CONFIG"] = os.environ["COVERAGE_PROCESS_CONFIG"]
        env["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), env.get("PATH", "")))
    env.update(
        {
            "PYTHONPATH": os.pathsep.join(
                (
                    *((str(ROOT / "tests" / "coverage_startup"),) if coverage_enabled else ()),
                    str(ROOT),
                    str(ROOT / "src"),
                )
            ),
            "PROXY_PORT": str(port),
            "PROXY_UPSTREAM_PORT": str(upstream),
            "PROXY_MODE": mode,
            "PROXY_LOG": str(log),
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "reference.loopback_proxy"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"proxy exited {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return proc
        except OSError:
            time.sleep(0.03)
    proc.terminate()
    raise TimeoutError("proxy did not bind")


@pytest.mark.parametrize("mode", ["drop", "delay", "strip"])
def test_real_loopback_intermediary(mode: str, tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite3"
    log = tmp_path / "proxy.jsonl"
    upstream = free_port()
    proxy_port = free_port()
    server = start_server(db, upstream)
    proxy = _start_proxy(proxy_port, upstream, mode, log)
    args = _args(f"proxy-{mode}")
    try:
        status, first = request(proxy_port, "create_guarded_issue", args, 10)
        assert status == 200 and first["result"]["resultType"] == "input_required"
        state = first["result"]["requestState"]
        if mode == "strip":
            status, denied = request(
                proxy_port, "create_guarded_issue", args, 11, state=state, body="alpha"
            )
            assert status >= 400 or "error" in denied
            expected_effects = 0
        else:
            with pytest.raises(
                (http.client.RemoteDisconnected, TimeoutError, ConnectionResetError, OSError)
            ):
                request(
                    proxy_port,
                    "create_guarded_issue",
                    args,
                    11,
                    state=state,
                    body="alpha",
                    timeout=0.2,
                )
            expected_effects = 1
        status, observed = request(
            proxy_port, "get_operation_status", {"operation_id": args["operation_id"]}, 12
        )
        assert status == 200
        value = observed["result"]["structuredContent"]
        assert value["freshWriteAuthorized"] is False
        if mode == "strip":
            assert value["state"] == "unknown" and value["storedResult"] is None
        else:
            assert value["state"] == "applied" and value["storedResult"] == "created 1"
        time.sleep(0.55 if mode == "delay" else 0.03)
    finally:
        stop_server(proxy)
        stop_server(server)
    with closing(sqlite3.connect(f"file:{db}?mode=ro", uri=True)) as conn:
        assert conn.execute("SELECT count(*) FROM issues").fetchone()[0] == expected_effects
        assert conn.execute("SELECT count(*) FROM operations").fetchone()[0] == expected_effects
    events = [json.loads(line) for line in log.read_text().splitlines()]
    names = [item["event"] for item in events]
    assert names.count("client_request") == names.count("upstream_request") == 3
    assert "upstream_response" in names
    if mode == "strip":
        client = [item for item in events if item["event"] == "client_request"][1]
        upstream_body = [item for item in events if item["event"] == "upstream_request"][1]
        assert b"requestState" in base64.b64decode(client["bodyBase64"])
        assert b"requestState" not in base64.b64decode(upstream_body["bodyBase64"])
    if mode == "drop":
        assert "dropped_response" in names
    if mode == "delay":
        assert "delayed_response" in names
