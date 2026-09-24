"""Verify a retained matrix with the exact committed source that produced it."""

from __future__ import annotations

import argparse
import io
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_MODULES = {"scripts.run_completion_matrix", "scripts.run_typescript_guarded_matrix"}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--module", choices=sorted(ALLOWED_MODULES), required=True)
    args = parser.parse_args()
    attempt = args.attempt.resolve(strict=True)
    try:
        relative_attempt = attempt.relative_to(ROOT)
    except ValueError as exc:
        raise SystemExit("attempt must be inside this repository") from exc
    if "raw" not in relative_attempt.parts:
        raise SystemExit("attempt must be a retained raw matrix directory")
    commit = subprocess.check_output(
        ["git", "-c", "core.fsmonitor=false", "rev-parse", "--verify", f"{args.source_commit}^{{commit}}"],
        cwd=ROOT, text=True,
    ).strip()
    archive = subprocess.check_output(["git", "-c", "core.fsmonitor=false", "archive", "--format=tar", commit], cwd=ROOT)
    with tempfile.TemporaryDirectory(prefix="mcr-committed-verifier-") as temporary:
        snapshot = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
            tar.extractall(snapshot, filter="data")
        retained = snapshot / relative_attempt
        if retained.exists():
            raise SystemExit("source archive already contains this attempt; refusing overwrite")
        shutil.copytree(attempt, retained)
        subprocess.run(
            [sys.executable, "-m", args.module, "--verify", str(retained)],
            cwd=snapshot,
            check=True,
        )


if __name__ == "__main__":
    main()
