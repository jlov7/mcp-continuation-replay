"""Bounded raw stdio MRTR capability probe for an isolated TypeScript SDK install."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from tests.wire_client import RawStdioClient

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node-modules", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    node_modules = args.node_modules.resolve()
    versions = {}
    modules = {}
    for name in ("server", "core"):
        package = node_modules / "@modelcontextprotocol" / name
        versions[name] = json.loads((package / "package.json").read_text())["version"]
        modules[name] = sha256(package / "dist" / "index.cjs")
    assert versions == {"server": "2.0.0", "core": "2.0.0"}
    server_script = ROOT / "scripts" / "current_typescript_mrtr_server.cjs"
    wire = RawStdioClient(
        ["env", f"NODE_PATH={node_modules}", "node", str(server_script)],
        output / "typescript-mrtr.transcript.log",
        output / "unused.sqlite3",
        timeout_s=8,
    )

    def call(params: dict, req_id: int) -> dict:
        frame = wire._frame("tools/call", params, req_id)
        frame["params"]["_meta"]["io.modelcontextprotocol/clientCapabilities"] = {
            "elicitation": {"form": {}}
        }
        wire.send(frame)
        reply = wire.recv()
        if reply.get("id") != req_id:
            raise AssertionError("request/reply id mismatch")
        return reply

    try:
        assert wire.open_connection()["resultType"] == "complete"
        arguments = {"operation_id": "synthetic-op"}
        first = call({"name": "probe_roundtrip", "arguments": arguments}, 10)
        assert first["result"]["resultType"] == "input_required"
        token = first["result"]["requestState"]
        assert isinstance(token, str) and token
        response = {"body": {"action": "accept", "content": {"body": "alpha"}}}
        second = call(
            {"name": "probe_roundtrip", "arguments": arguments, "inputResponses": response, "requestState": token},
            11,
        )
        assert second["result"]["resultType"] == "complete"
        assert second["result"]["structuredContent"] == {"operation_id": "synthetic-op", "accepted": True}
        position = len(token) // 2
        tampered = token[:position] + ("A" if token[position] != "A" else "B") + token[position + 1 :]
        rejected = call(
            {"name": "probe_roundtrip", "arguments": arguments, "inputResponses": response, "requestState": tampered},
            12,
        )
        assert rejected["error"]["code"] == -32602
    finally:
        wire.close()
    result = {
        "status": "pass",
        "scope": "stable TypeScript SDK stdio input_required, signed requestState roundtrip and tamper rejection only",
        "matrix_case_status": "unsupported: no TypeScript guarded SQLite server implementing the frozen matrix boundary",
        "request_protocol_version": "2026-07-28",
        "sdk_versions": versions,
        "sdk_module_sha256": modules,
        "probe_server_sha256": sha256(server_script),
        "transcript_sha256": sha256(output / "typescript-mrtr.transcript.log"),
    }
    (output / "capability.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
