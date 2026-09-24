from __future__ import annotations

from scripts.run_portable_vectors import classify, evaluate


def test_portable_vectors_and_planted_unsafe_implementation() -> None:
    assert all(row["actual"] == row["expected"] for row in evaluate())

    def ignores_accepted_response(base: dict, vector: dict, key: bytes) -> str:
        # Planted unsafe implementation binds state and arguments but drops
        # accepted input responses before checking an existing operation.
        changes = dict(vector.get("changes", {}))
        changes.pop("input_responses", None)
        return classify(base, {**vector, "changes": changes}, key)

    outcomes = evaluate(classifier=ignores_accepted_response)
    changed = next(row for row in outcomes if row["name"] == "changed_accepted_input")
    assert changed == {"name": "changed_accepted_input", "expected": "conflict", "actual": "replay"}
