"""One local adapter for the versioned, implementation-neutral continuation vectors."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path

from continuation_replay.fingerprint import LogicalRequest, fingerprint
from reference.backend import OperationIdentity
from reference.consumer import ContinuationConsumer
from reference.readback import EffectObservation

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / "research" / "portable-continuation-v1.json"


def classify(base: dict, vector: dict, key: bytes) -> str:
    candidate = {**base, **vector.get("changes", {})}
    if candidate["continuation_state"] is None:
        return "reject"
    if vector.get("transport") in {"lost_reply", "lost_reply_missing_record"}:
        identity = OperationIdentity("op-1", base["principal"], "sqlite:vector")
        consumer = ContinuationConsumer(identity)
        uncertain = consumer.transport_failed(TimeoutError("lost reply"))
        if uncertain.action != "reconcile":
            raise AssertionError("transport loss did not preserve uncertainty")
        applied = vector["transport"] == "lost_reply"
        observed = EffectObservation(
            identity=identity,
            observed_at="2000-01-01T00:00:00+00:00",
            authoritative=True,
            scope="operation ledger and physical effect",
            state="applied" if applied else "unknown",
            matching_ids=(1,) if applied else (),
            stored_result="created 1" if applied else None,
            scope_binding=identity,
        )
        decision = consumer.reconcile(lambda _: observed)
        if applied:
            return "status_only" if decision.stored_result == "created 1" else "invalid"
        return (
            "stop_unknown"
            if decision.effect == "unknown" and decision.action == "stop"
            else "invalid"
        )
    first = fingerprint(LogicalRequest(**base), key=key)
    second = fingerprint(LogicalRequest(**candidate), key=key)
    return "replay" if first == second else "conflict"


def evaluate(
    path: Path = DEFAULT,
    classifier: Callable[[dict, dict, bytes], str] = classify,
) -> list[dict[str, str]]:
    pack = json.loads(path.read_text(encoding="utf-8"))
    if pack.get("version") != 1:
        raise ValueError("unsupported vector version")
    key = bytes.fromhex(pack["keyHex"])
    return [
        {
            "name": vector["name"],
            "expected": vector["expected"],
            "actual": classifier(pack["base"], vector, key),
        }
        for vector in pack["vectors"]
    ]


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    outcomes = evaluate(path)
    print(json.dumps(outcomes, indent=2))
    return 0 if all(row["actual"] == row["expected"] for row in outcomes) else 1


if __name__ == "__main__":
    raise SystemExit(main())
