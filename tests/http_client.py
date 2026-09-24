"""Raw local HTTP MRTR client; records exactly what crossed its boundary."""

from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from tests.test_guarded_wire_matrix import BACKEND, FINGERPRINT_KEY_HEX, STATE_KEY_HEX, T0
from tests.wire_client import MODERN_ENVELOPE

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(db: Path, port: int) -> subprocess.Popen[bytes]:
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
            "WIRE_SERVER_DB": str(db),
            "WIRE_BACKEND_ID": BACKEND,
            "WIRE_PRINCIPAL": "unused-http-test-default",
            "WIRE_CLOCK_EPOCH": str(T0),
            "WIRE_AUTHORITY_TTL": "300",
            "WIRE_REPLAY_RETENTION_TTL": "360",
            "WIRE_REQUEST_STATE_TTL": "600",
            "WIRE_STATE_KEY_HEX": STATE_KEY_HEX,
            "WIRE_FINGERPRINT_KEY_HEX": FINGERPRINT_KEY_HEX,
            "WIRE_HTTP_PORT": str(port),
        }
    )
    proc = subprocess.Popen(
        [sys.executable, "-m", "reference.loopback_http"],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            tail = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
            raise RuntimeError(f"HTTP server exited {proc.returncode}: {tail}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return proc
        except OSError:
            time.sleep(0.03)
    proc.terminate()
    raise TimeoutError("HTTP server did not bind")


def stop_server(proc: subprocess.Popen[bytes]) -> None:
    proc.terminate()
    try:
        proc.communicate(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate(timeout=4)


def request(
    port: int,
    name: str,
    arguments: dict[str, Any],
    request_id: int,
    *,
    principal: str = "alice",
    state: str | None = None,
    body: str | None = None,
    path: str = "/mcp",
    timeout: float = 4,
) -> tuple[int, dict]:
    params: dict[str, Any] = {"_meta": MODERN_ENVELOPE, "name": name, "arguments": arguments}
    if state is not None:
        params["requestState"] = state
    if body is not None:
        params["inputResponses"] = {"body": {"action": "accept", "content": {"body": body}}}
    frame = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": params}
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body=json.dumps(frame).encode(),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "MCP-Protocol-Version": "2026-07-28",
                "Mcp-Method": "tools/call",
                "Mcp-Name": name,
                "Authorization": f"Bearer test-{principal}-v1",
            },
        )
        response = conn.getresponse()
        payload = response.read()
        return response.status, json.loads(payload) if payload.startswith(b"{") else {
            "raw": payload.decode()
        }
    finally:
        conn.close()
