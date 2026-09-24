"""Raw newline-delimited JSON-RPC client for WIRE-LEVEL evidence.

Talking to the SDK server with the SDK client again would prove nothing new:
in-process and object-level paths can hide transport loss. This client speaks
the MCP 2026-07-28 MODERN stdio framing directly and records every byte in both
directions to a transcript.

Two facts from reading the SDK's runner make this client what it is:
- `serve_dual_era_loop` picks the protocol era from the CLIENT'S FIRST REQUEST.
  The first non-initialize request carrying the modern `_meta` envelope opens a
  2026-07-28 connection; sending `initialize` forces the legacy era, where the
  MRTR result types cannot be serialized.
- In the modern era there is NO `initialize` handshake at all. Every request
  carries its own envelope: `_meta` with the reserved `io.modelcontextprotocol/*`
  keys. Notifications are envelope-free.

Every test that uses this client is evidence about the wire, not about objects.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_VERSION = "2026-07-28"
MODERN_ENVELOPE = {
    "io.modelcontextprotocol/protocolVersion": PROTOCOL_VERSION,
    "io.modelcontextprotocol/clientInfo": {"name": "wire-replayer", "version": "0.0.1"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


class WireError(RuntimeError):
    """The reference server refused or misbehaved on the wire."""


class RawStdioClient:
    """One subprocess server plus a transcript of every byte."""

    def __init__(
        self,
        server_cmd: list[str],
        transcript_path: Path,
        db_path: Path,
        timeout_s: float = 20.0,
        extra_env: dict[str, str] | None = None,
        backend_id: str = "sqlite:wire-test",
    ) -> None:
        self._t = transcript_path.open("w")
        self.db_path = db_path
        env = {
            key: value
            for key, value in os.environ.items()
            if key in {"PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT"}
        }
        coverage_enabled = bool(os.environ.get("COVERAGE_PROCESS_CONFIG"))
        if coverage_enabled:
            env["COVERAGE_PROCESS_CONFIG"] = os.environ["COVERAGE_PROCESS_CONFIG"]
            env["PATH"] = os.pathsep.join((str(Path(sys.executable).parent), env.get("PATH", "")))
        env["PYTHONPATH"] = os.pathsep.join(
            (
                *((str(ROOT / "tests" / "coverage_startup"),) if coverage_enabled else ()),
                str(ROOT), str(ROOT / "src"), env.get("PYTHONPATH", ""),
            )
        )  # spawned process lacks pytest's pythonpath
        env["WIRE_SERVER_DB"] = str(
            db_path
        )  # per-test DB; the server must never have its file unlinked
        env["WIRE_BACKEND_ID"] = backend_id
        if extra_env:
            allowed = {
                "WIRE_FAULT",
                "WIRE_PRINCIPAL",
                "WIRE_CLOCK_EPOCH",
                "WIRE_AUTHORITY_TTL",
                "WIRE_REPLAY_RETENTION_TTL",
                "WIRE_REQUEST_STATE_TTL",
                "WIRE_STATE_KEY_HEX",
                "WIRE_FINGERPRINT_KEY_HEX",
            }
            unexpected = set(extra_env) - allowed
            if unexpected:
                raise ValueError(f"unsupported server environment keys: {sorted(unexpected)!r}")
            env.update(extra_env)
        self._proc = subprocess.Popen(
            server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        self._timeout = timeout_s
        self._next_id = 1

    def _read_line(self) -> bytes:
        stdout = self._proc.stdout
        if stdout is None:
            raise WireError("server stdout closed")
        ready, _, _ = select.select([stdout], [], [], self._timeout)
        if not ready:
            self.close()
            raise TimeoutError(f"no wire reply within {self._timeout:.0f}s")
        line = stdout.readline()
        if not line:
            tail = self._stderr_tail()
            self.close()
            raise WireError(f"server closed stdout; stderr={tail}")
        return line

    def send(self, obj: dict) -> None:
        line = json.dumps(obj, separators=(",", ":")) + "\n"
        self._t.write(f"> {line}")
        self._t.flush()
        if self._proc.stdin is None:
            raise WireError("server stdin closed")
        try:
            self._proc.stdin.write(line.encode())
            self._proc.stdin.flush()
        except BrokenPipeError:
            raise WireError(f"broken pipe; stderr={self._stderr_tail()}") from None

    def recv(self) -> dict:
        line = self._read_line().decode("utf-8")
        self._t.write(f"< {line}")
        self._t.flush()
        try:
            message = json.loads(line)
        except json.JSONDecodeError as e:
            raise WireError(f"non-JSON on wire: {line[:200]!r} ({e})") from None
        if not isinstance(message, dict):
            raise WireError(f"non-object JSON-RPC message: {message!r}")
        return message

    def _frame(self, method: str, params: dict, req_id: int) -> dict:
        """A modern-era request: `_meta` envelope is sibling of the method params."""
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": {"_meta": MODERN_ENVELOPE, **params},
        }

    def request(self, method: str, params: dict, req_id: int | None = None) -> dict:
        req_id = req_id if req_id is not None else self._next_id
        self._next_id = max(self._next_id, req_id) + 1
        self.send(self._frame(method, params, req_id))
        msg = self.recv()
        if msg.get("id") != req_id:
            raise WireError(f"id mismatch: sent {req_id}, got {msg.get('id')!r}")
        if "error" in msg:
            raise WireError(f"wire error for {method}: {msg['error']}")
        if "result" not in msg or not isinstance(msg["result"], dict):
            raise WireError(f"missing object result for {method}: {msg!r}")
        return msg["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        frame: dict = {"jsonrpc": "2.0", "method": method}
        if params:
            frame["params"] = params
        self.send(frame)

    def open_connection(self) -> dict:
        """First request decides the era: `tools/list` with the modern envelope."""
        return self.request("tools/list", {})

    @property
    def returncode(self) -> int | None:
        return self._proc.poll()

    def close(self) -> None:
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait(timeout=5)
        for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        if not self._t.closed:
            self._t.close()

    def _stderr_tail(self) -> str:
        if self._proc.stderr is None or self._proc.stderr.closed:
            return ""
        ready, _, _ = select.select([self._proc.stderr], [], [], 0)
        if not ready:
            return ""
        tail = self._proc.stderr.read(2000)
        return tail.decode("utf-8", "replace")[-2000:]
