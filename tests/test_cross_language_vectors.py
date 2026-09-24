"""Cross-language fingerprint parity (Milestone D).

For every shared vector in `tests/fixtures/fingerprint_vectors.json`, the
Python adapter and the TypeScript adapter MUST produce byte-identical SHA-256
fingerprints. This is the interoperability contract: a logical operation has
ONE identity no matter which language computes it.

This is cross-implementation testing, NOT independent validation — both files
are written by the same author. The README states this plainly.

Vectors 01/08/09 encode the SAME logical operation and MUST coincide; vectors
04/06/11 differ materially and MUST NOT collide. Those assertions make the
digest meaningful, not just equal.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from continuation_replay.fingerprint import LogicalRequest, fingerprint

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "fingerprint_vectors.json"
TS_CLI = ROOT / "adapters" / "typescript" / "src" / "cli.ts"
TEST_KEY = b"test-only-cross-language-key-32b"
assert len(TEST_KEY) >= 32

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is required to run the TypeScript adapter",
)


def _ts_fingerprints(vectors: list[dict]) -> dict[str, str]:
    """Run the TS adapter CLI and parse its `name\tfingerprint` lines."""
    lines = [
        json.dumps({"name": v["name"], "request": v["request"]}, separators=(",", ":"))
        for v in vectors
    ]
    proc = subprocess.run(
        ["node", str(TS_CLI)],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT / "adapters" / "typescript"),
        check=False,
        env={
            **os.environ,
            "CONTINUATION_REPLAY_FINGERPRINT_KEY_HEX": TEST_KEY.hex(),
        },
    )
    if proc.returncode != 0:
        raise AssertionError(f"TS adapter failed: {proc.stderr[-2000:]}")
    out: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        name, _, digest = line.partition("\t")
        out[name] = digest
    return out


def _py_fingerprints(vectors: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in vectors:
        r = v["request"]
        out[v["name"]] = fingerprint(
            LogicalRequest(
                principal=r.get("principal"),
                tool_id=r["tool_id"],
                tool_version=r["tool_version"],
                arguments=r.get("arguments", {}),
                continuation_state=r.get("continuation_state"),
                input_responses=r.get("input_responses"),
            ),
            key=TEST_KEY,
        )
    return out


def test_every_shared_vector_fingerprints_identically_across_languages() -> None:
    data = json.loads(FIXTURES.read_text())
    vectors: list[dict] = data["vectors"]
    py = _py_fingerprints(vectors)
    ts = _ts_fingerprints(vectors)

    assert set(py) == set(ts), f"name mismatch: {set(py) ^ set(ts)}"
    for name in py:
        assert py[name] == ts[name], (
            f"fingerprint divergence on {name}: python={py[name]} ts={ts[name]}"
        )


def test_identical_logical_operations_coincide() -> None:
    data = json.loads(FIXTURES.read_text())
    vectors = {v["name"]: v["request"] for v in data["vectors"]}
    py = _py_fingerprints([{"name": n, "request": vectors[n]} for n in vectors])
    ts = _ts_fingerprints([{"name": n, "request": vectors[n]} for n in vectors])

    for impl in (py, ts):
        assert impl["01_identical_retry"] == impl["08_concurrent_attempt_a"], (
            f"{impl} split identical operations 01/08"
        )
    assert py["01_identical_retry"] == py["08_concurrent_attempt_a"] == ts["01_identical_retry"]


def test_materially_different_operations_differ() -> None:
    data = json.loads(FIXTURES.read_text())
    vectors = {v["name"]: v["request"] for v in data["vectors"]}
    py = _py_fingerprints([{"name": n, "request": vectors[n]} for n in vectors])
    ts = _ts_fingerprints([{"name": n, "request": vectors[n]} for n in vectors])

    differing_pairs = [
        ("04_changed_input_responses", "01_identical_retry"),
        ("06_different_principal", "01_identical_retry"),
        ("11_metadata_stripped", "01_identical_retry"),
    ]
    for impl in (py, ts):
        for a, b in differing_pairs:
            assert impl[a] != impl[b], f"{impl} failed to distinguish {a}/{b}"


def test_unsafe_control_vector_is_distinct_from_admitted_operation() -> None:
    """The unsafe new-identity retry carries no continuation — it must not
    fingerprint as the same logical operation as an admitted continuation."""
    data = json.loads(FIXTURES.read_text())
    vectors = {v["name"]: v["request"] for v in data["vectors"]}
    py = _py_fingerprints([{"name": n, "request": vectors[n]} for n in vectors])
    ts = _ts_fingerprints([{"name": n, "request": vectors[n]} for n in vectors])
    assert py["unsafe_new_identity_retry"] != py["01_identical_retry"]
    assert ts["unsafe_new_identity_retry"] != ts["01_identical_retry"]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (1.5, "number must be an integer"),
        (2**53, "outside the interoperable safe range"),
    ],
)
def test_python_rejects_non_interoperable_numbers(value: object, message: str) -> None:
    request = LogicalRequest(
        principal="alice", tool_id="create_issue", tool_version="1", arguments={"n": value}
    )
    with pytest.raises(ValueError, match=message):
        fingerprint(request, key=TEST_KEY)


def test_python_normalizes_integral_float_to_json_integer() -> None:
    float_request = LogicalRequest(
        principal="alice", tool_id="tool", tool_version="1", arguments={"n": 1.0}
    )
    int_request = LogicalRequest(
        principal="alice", tool_id="tool", tool_version="1", arguments={"n": 1}
    )
    assert fingerprint(float_request, key=TEST_KEY) == fingerprint(int_request, key=TEST_KEY)


def test_both_adapters_reject_unpaired_surrogate() -> None:
    request = {
        "principal": "alice",
        "tool_id": "tool",
        "tool_version": "1",
        "arguments": {"bad": "\ud800"},
    }
    with pytest.raises(ValueError, match="surrogate"):
        _py_fingerprints([{"name": "bad", "request": request}])
    proc = subprocess.run(
        ["node", str(TS_CLI)],
        input=json.dumps({"name": "bad", "request": request}) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(ROOT / "adapters" / "typescript"),
        check=False,
        env={
            **os.environ,
            "CONTINUATION_REPLAY_FINGERPRINT_KEY_HEX": TEST_KEY.hex(),
        },
    )
    assert proc.returncode == 2
    assert "surrogate" in proc.stderr
