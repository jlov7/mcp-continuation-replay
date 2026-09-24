"""Rebuild a concise table from an already verified retained matrix attempt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.run_completion_matrix import verify


def render(attempt: Path) -> str:
    counts = verify(attempt)
    records = [json.loads(line) for line in (attempt / "results.jsonl").read_text().splitlines()]
    provenance = json.loads((attempt / "provenance.json").read_text())
    lines = [
        "# Guarded stdio completion matrix",
        "",
        f"Source commit: `{provenance['source_head']}`. Frozen protocol commit: `{provenance['protocol_commit']}`.",
        f"Requested {counts['requested']}; executed {counts['executed']}; passed {counts['passed']}.",
        "",
        "| Case | Expected classification | Status | SQLite issues | Wire replies |",
        "|---|---|---|---:|---:|",
    ]
    for record in records:
        lines.append(
            f"| {record['case_id']} | {record['expected']} | {record['status']} | "
            f"{len(record['independent_db']['issues'])} | "
            f"{len(record['independent_wire']['replies'])} |"
        )
    lines.extend(["", "Derived from `results.jsonl`. Raw transcripts and SQLite files remain in each case directory.", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    path = args.attempt.resolve()
    target = path / "MATRIX.md"
    content = render(path)
    if target.exists():
        if target.read_text() != content:
            raise ValueError("existing derived matrix does not match retained evidence")
    else:
        target.write_text(content)
    print(target)


if __name__ == "__main__":
    main()
