"""Check that an sdist carries exactly the tracked retained SQLite snapshots."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path, PurePosixPath


def git(*args: str) -> bytes:
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def tracked_sqlite(commit: str) -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    for record in git("ls-tree", "-rz", commit).split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        path = raw_path.decode("utf-8")
        if not path.endswith(".sqlite3"):
            continue
        mode, kind, object_id = metadata.decode("ascii").split()
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"tracked SQLite path is not a regular file: {path}")
        expected[path] = git("cat-file", "blob", object_id)
    if not expected:
        raise ValueError("HEAD contains no tracked SQLite snapshots")
    return expected


def verify(sdist: Path) -> dict[str, str | int]:
    commit = git("rev-parse", "HEAD^{commit}").decode("ascii").strip()
    expected = tracked_sqlite(commit)
    archive_bytes = sdist.read_bytes()
    actual: dict[str, bytes] = {}
    archive_root: str | None = None
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            if not member.name.endswith(".sqlite3"):
                continue
            parts = member.name.split("/")
            if (
                len(parts) < 3
                or any(part in {"", ".", ".."} for part in parts)
                or "\\" in member.name
                or PurePosixPath(member.name).is_absolute()
            ):
                raise ValueError(f"unsafe SQLite archive path: {member.name}")
            if archive_root is None:
                archive_root = parts[0]
            elif archive_root != parts[0]:
                raise ValueError(f"inconsistent SQLite archive root: {member.name}")
            path = "/".join(parts[1:])
            if path in actual:
                raise ValueError(f"duplicate SQLite archive path: {path}")
            if not member.isfile():
                raise ValueError(f"SQLite archive member is not a regular file: {path}")
            source = archive.extractfile(member)
            if source is None:
                raise ValueError(f"cannot read SQLite archive member: {path}")
            actual[path] = source.read()
    missing = expected.keys() - actual.keys()
    extra = actual.keys() - expected.keys()
    if missing or extra:
        raise ValueError(
            f"SQLite archive inventory differs: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for path, source in expected.items():
        if actual[path] != source:
            raise ValueError(f"SQLite archive bytes differ from HEAD: {path}")
    return {
        "sdist": str(sdist),
        "tracked_commit": commit,
        "sqlite_snapshots": len(expected),
        "sdist_sha256": hashlib.sha256(archive_bytes).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.sdist), sort_keys=True))
    except (OSError, ValueError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        parser.exit(1, f"sdist SQLite verification failed: {exc}\n")


if __name__ == "__main__":
    main()
