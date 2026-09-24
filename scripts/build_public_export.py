"""Build a deterministic, history-free public ZIP and extracted source tree.

Run only from a clean committed checkout. The ZIP digest must be recorded outside
the archive as the release receipt; it binds the manifest excluded from itself.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
import tarfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from scripts.verify_public_export import (
    DERIVATIVE_PATHS,
    MANIFEST,
    PUBLIC_DERIVATIVE_PROVENANCE,
    _unique_object,
    verify_inventory,
)

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "MCP Continuation Replay"
HOME_PATTERN = re.compile(rb"/Users/[^\s\x27\x22]+")
PYTEST_PATTERN = re.compile(rb"pytest-of-[A-Za-z0-9._-]+")
REDACTIONS = {
    "artifacts/evidence/wire-replay-run.txt": "home",
    "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184055Z-1790102455601597000/case-08.pytest.stdout.log": "pytest",
    "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184055Z-1790102455601597000/results.jsonl": "home",
    "docs/research-completion-2026-09-22/verification/fresh-install.log": "home",
    "docs/research-completion-2026-09-22/verification/native-python-and-v2.log": "home",
}
assert set(REDACTIONS) == DERIVATIVE_PATHS


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def detect_source_kind(root: Path = ROOT) -> str:
    """Classify only by the five approved derivative bytes, never by Git history."""
    matched = [
        _sha256((root / name).read_bytes()) == hashes[0]
        for name, hashes in PUBLIC_DERIVATIVE_PROVENANCE.items()
    ]
    if all(matched):
        return "already-public"
    if any(matched):
        raise ValueError("mixed private and public derivative bytes")
    return "private-origin"


def _git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-c", "core.fsmonitor=false", *args], cwd=ROOT)


def _clean_head() -> str:
    if _git("status", "--porcelain"):
        raise ValueError("source checkout is not clean; commit reviewed changes first")
    return _git("rev-parse", "HEAD").decode().strip()


def _blocked_path(name: str) -> bool:
    forbidden = {
        ".git",
        ".secrets",
        "credentials",
        "node_modules",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".git-credentials",
        ".ssh",
        ".aws",
        ".gnupg",
        "id_rsa",
        "id_ed25519",
    }
    suffixes = (".pem", ".p12", ".pfx", ".key")
    return any(
        part.casefold() in forbidden
        or part.casefold().startswith(".env")
        or part.casefold().endswith(suffixes)
        for part in PurePosixPath(name).parts
    )


def _source_tree(commit: str, *, already_public: bool = False) -> dict[str, tuple[str, str]]:
    tree: dict[str, tuple[str, str]] = {}
    portable: set[str] = set()
    for record in _git("ls-tree", "-r", "-z", commit).split(b"\0"):
        if not record:
            continue
        header, raw_path = record.split(b"\t", 1)
        mode, kind, blob = header.decode("ascii").split(" ")
        name = raw_path.decode("utf-8", "strict")
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or (name == MANIFEST and not already_public)
        ):
            raise ValueError(f"unsafe tracked path: {name}")
        if _blocked_path(name):
            raise ValueError(f"credential/runtime path tracked: {name}")
        folded = unicodedata.normalize("NFC", name).casefold()
        if folded in portable:
            raise ValueError(f"case/Unicode tracked path collision: {name}")
        portable.add(folded)
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError(f"unsupported tracked object: {name} ({mode} {kind})")
        tree[name] = (mode, blob)
    return tree


def _redact(name: str, source: bytes) -> tuple[bytes, list[dict[str, object]]]:
    kind = REDACTIONS.get(name)
    if kind is None:
        return source, []
    pattern, replacement, label, prefix = (
        (HOME_PATTERN, b"<REDACTED_HOME>", "absolute_home_path_to_<REDACTED_HOME>", "/Users/<user>")
        if kind == "home"
        else (
            PYTEST_PATTERN,
            b"pytest-of-<REDACTED_USER>",
            "pytest_temp_username_to_<REDACTED_USER>",
            "pytest-of-<user>",
        )
    )
    transformed, count = pattern.subn(replacement, source)
    if count == 0 or transformed == source:
        raise ValueError(f"expected private path for redaction absent: {name}")
    return transformed, [{"matched_prefix": prefix, "occurrences": count, "transform": label}]


def _private_origin_commit(prior: bytes | None) -> str | None:
    if prior is None:
        return None
    manifest = json.loads(prior, object_pairs_hook=_unique_object)
    if not isinstance(manifest, dict):
        raise TypeError("prior public manifest is not an object")
    fmt = manifest.get("format")
    if fmt == "public-source-export-v3" and manifest.get("source_kind") == "already_public":
        origin = manifest.get("origin_private_commit")
    elif fmt == "public-source-export-v2":
        origin = manifest.get("source_commit")
    else:
        raise ValueError("unsupported prior public manifest")
    if origin is not None and (
        not isinstance(origin, str) or re.fullmatch(r"[0-9a-f]{40}", origin) is None
    ):
        raise ValueError("invalid prior private origin commit")
    return origin


def build(destination: Path, *, already_public: bool = False) -> dict[str, str | int]:
    commit = _clean_head()
    tree = _source_tree(commit, already_public=already_public)
    archive = _git("archive", "--format=tar", commit)
    staged = destination / f"mcp-continuation-replay-{commit[:8]}"
    zip_path = destination / f"mcp-continuation-replay-{commit[:8]}.zip"
    if staged.exists() or zip_path.exists():
        raise ValueError("candidate path exists; refuse overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    staged.mkdir()
    entries: list[dict[str, object]] = []
    prior_manifest: bytes | None = None
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as tar:
        members = tar.getmembers()
        archive_files = {member.name for member in members if member.isfile()}
        if archive_files != set(tree):
            raise ValueError("archive differs from tracked tree inventory")
        if any(not member.isfile() and not member.isdir() for member in members):
            raise ValueError("archive contains a link or unsupported member")
        for member in members:
            if member.isdir():
                continue
            name = member.name
            path = PurePosixPath(name)
            if (
                path.is_absolute()
                or ".." in path.parts
                or (name == MANIFEST and not already_public)
                or name.startswith(".git/")
            ):
                raise ValueError(f"unsafe source archive path: {name}")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError(f"cannot read source archive file: {name}")
            source = stream.read()
            mode = "100755" if member.mode & 0o111 else "100644"
            expected_mode, expected_blob = tree[name]
            blob_hash = hashlib.sha1(
                b"blob " + str(len(source)).encode() + b"\0" + source
            ).hexdigest()
            if mode != expected_mode or blob_hash != expected_blob:
                raise ValueError(f"archive source content or mode mismatch: {name}")
            if name == MANIFEST and already_public:
                if mode != "100644":
                    raise ValueError("prior public manifest mode mismatch")
                prior_manifest = source
                continue
            if already_public:
                data, transforms = source, []
                if (
                    name in DERIVATIVE_PATHS
                    and _sha256(source) != PUBLIC_DERIVATIVE_PROVENANCE[name][0]
                ):
                    raise ValueError(f"approved public derivative changed: {name}")
            else:
                data, transforms = _redact(name, source)
                if (
                    name in DERIVATIVE_PATHS
                    and _sha256(data) != PUBLIC_DERIVATIVE_PROVENANCE[name][0]
                ):
                    raise ValueError(f"private redaction changed approved derivative: {name}")
            target = staged / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            target.chmod(0o755 if mode == "100755" else 0o644)
            entry: dict[str, object] = {
                "path": name,
                "git_mode": mode,
                "git_blob_sha1": blob_hash,
                "original_sha256": _sha256(source),
                "exported_sha256": _sha256(data),
                "status": (
                    "retained_redacted_derivative"
                    if already_public and name in DERIVATIVE_PATHS
                    else "redacted_derivative"
                    if transforms
                    else "byte_identical"
                ),
                "transforms": transforms,
            }
            if transforms:
                entry["contract"] = (
                    "source hash and deterministic path transform recorded; private original bytes unavailable in public export"
                )
            if already_public and name in DERIVATIVE_PATHS:
                _, private_sha, private_blob = PUBLIC_DERIVATIVE_PROVENANCE[name]
                entry["private_origin_sha256"] = private_sha
                entry["private_origin_git_blob_sha1"] = private_blob
                entry["contract"] = (
                    "Current Git blob is already redacted; fixed private-origin hashes are provenance assertions only."
                )
            entries.append(entry)
    if set(REDACTIONS) - {str(entry["path"]) for entry in entries}:
        raise ValueError("redaction target absent from committed source")
    prior_commit = _private_origin_commit(prior_manifest) if already_public else None
    omissions = (
        [{"path": MANIFEST, "reason": "superseded_tracked_manifest"}]
        if prior_manifest is not None
        else []
    )
    manifest: dict[str, object] = {
        "format": "public-source-export-v3" if already_public else "public-source-export-v2",
        "project": PROJECT,
        "source_commit": commit,
        "tracked_source_file_count": len(tree),
        "exported_file_count": len(entries),
        "omitted_file_count": len(omissions),
        "omissions": omissions,
        "privacy_contract": (
            "Public Git tree contains five already-redacted historical derivatives; their private originals remain unavailable."
            if already_public
            else "Git history, untracked files, caches, environments, dependencies and runtime state excluded; five fixed path derivatives disclosed."
        ),
        "files": sorted(entries, key=lambda entry: str(entry["path"])),
    }
    if already_public:
        manifest["source_kind"] = "already_public"
        manifest["origin_private_commit"] = prior_commit
    (staged / MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (staged / MANIFEST).chmod(0o644)
    verify_inventory(staged)
    if _clean_head() != commit:
        raise ValueError("source HEAD or working tree changed during export")
    with zipfile.ZipFile(
        zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as zip_file:
        for path in sorted(staged.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(staged).as_posix()
            mode = path.stat().st_mode & 0o777
            info = zipfile.ZipInfo(f"{staged.name}/{relative}", date_time=(2026, 9, 22, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100000 | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            zip_file.writestr(
                info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9
            )
    if _clean_head() != commit:
        raise ValueError("source HEAD or working tree changed during ZIP creation")
    return {
        "source_commit": commit,
        "exported_file_count": len(entries),
        "manifest_sha256": _sha256((staged / MANIFEST).read_bytes()),
        "archive_sha256": _sha256(zip_path.read_bytes()),
        "archive": str(zip_path),
        "extracted_root": str(staged),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument(
        "--source-kind",
        choices=("private-origin", "already-public"),
        default="private-origin",
        help="Declare whether committed source has private originals or approved public derivatives",
    )
    args = parser.parse_args()
    try:
        print(
            json.dumps(
                build(args.destination, already_public=args.source_kind == "already-public"),
                indent=2,
                sort_keys=True,
            )
        )
    except (
        OSError,
        TypeError,
        ValueError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        parser.exit(1, f"public export build failed: {exc}\n")


if __name__ == "__main__":
    main()
