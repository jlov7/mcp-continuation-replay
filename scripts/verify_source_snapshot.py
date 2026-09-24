"""Verify a retained matrix without Git history using an exact source snapshot."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ALLOWED_MODULES = {"scripts.run_completion_matrix", "scripts.run_typescript_guarded_matrix"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--attempt", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.snapshot_manifest.read_text())
    attempt = args.attempt.resolve(strict=True)
    if manifest["module"] not in ALLOWED_MODULES:
        raise SystemExit("snapshot names an unsupported verifier module")
    relative_attempt = Path(manifest["attempt_relative_path"])
    if relative_attempt.is_absolute() or ".." in relative_attempt.parts or "raw" not in relative_attempt.parts:
        raise SystemExit("invalid attempt path in snapshot manifest")
    provenance = json.loads((attempt / "provenance.json").read_text())
    if provenance["source_head"] != manifest["source_commit"]:
        raise SystemExit("attempt source commit does not match snapshot")
    if provenance["source_hashes"] != manifest["source_hashes"]:
        raise SystemExit("attempt source hashes do not match snapshot")
    if digest((attempt / "SUMMARY.json").read_bytes()) != manifest["summary_sha256"]:
        raise SystemExit("attempt summary differs from snapshot receipt")
    archive = args.snapshot_manifest.with_suffix(".tar.gz")
    data = archive.read_bytes()
    if digest(data) != manifest["archive_sha256"]:
        raise SystemExit("source snapshot archive hash mismatch")
    with tempfile.TemporaryDirectory(prefix="mcr-source-snapshot-") as temporary:
        root = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
            members = tar.getmembers()
            if {member.name for member in members} != set(manifest["source_hashes"]):
                raise SystemExit("source snapshot file inventory mismatch")
            for member in members:
                path = Path(member.name)
                if not member.isfile() or path.is_absolute() or ".." in path.parts:
                    raise SystemExit("invalid source snapshot member")
                content = tar.extractfile(member)
                if content is None or digest(content.read()) != manifest["source_hashes"][member.name]:
                    raise SystemExit(f"source snapshot hash mismatch: {member.name}")
            tar.extractall(root, filter="data")
        retained = root / relative_attempt
        if retained.exists():
            raise SystemExit("source snapshot already contains attempt path")
        shutil.copytree(attempt, retained)
        subprocess.run([sys.executable, "-m", manifest["module"], "--verify", str(retained)], cwd=root, check=True)


if __name__ == "__main__":
    main()
