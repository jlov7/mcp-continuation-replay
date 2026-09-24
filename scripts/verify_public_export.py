"""Verify a history-free public export and its retained canonical matrices.

The manifest lists every regular file except itself. The archive's SHA-256,
recorded outside the archive, binds the manifest and this verifier together.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

MANIFEST = "EXPORT-MANIFEST.json"
DERIVATIVE_PATHS = {
    "artifacts/evidence/wire-replay-run.txt",
    "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184055Z-1790102455601597000/case-08.pytest.stdout.log",
    "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184055Z-1790102455601597000/results.jsonl",
    "docs/research-completion-2026-09-22/verification/fresh-install.log",
    "docs/research-completion-2026-09-22/verification/native-python-and-v2.log",
}
# Approved public bytes and private-source provenance for the five historical
# derivatives. Public re-exports never need or read the private originals.
PUBLIC_DERIVATIVE_PROVENANCE = {
    "artifacts/evidence/wire-replay-run.txt": (
        "d2e246d062ffd711e7bacb47eb08ebc2d0904ef3256f9cd5b04a049bd6535bf8",
        "4f32aa2f11b97b333082fd62334947e4d2afd4bb460c77dcfef0e044b5e33bc5",
        "07fee55f38360a93fb1ac57187dbd3c21fb99df9",
    ),
    "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184055Z-1790102455601597000/case-08.pytest.stdout.log": (
        "bebf3f505c147177ee707efda7ac0e743bb83f33765d49a86ccb711eb453c3dc",
        "e5777d04c59473d6d1121d96ec3ff116bbbcdbd8f52feb2db9d653629e22db18",
        "d4092d040f93ec51ed7c86cef967d910cc04ab55",
    ),
    "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184055Z-1790102455601597000/results.jsonl": (
        "83510cdd5e60b0d7ecf55e93b3cbae75333b5b11b1492ecdd5ed5b032a97c1b4",
        "19306c698f53f15f7d9c1cd6416d44ec02d0aa898a3a14c841f6792a0165273e",
        "0b121fa17886e7799a1235228ed0a577d93dd37b",
    ),
    "docs/research-completion-2026-09-22/verification/fresh-install.log": (
        "5c04bd519c035f41d195d7438b2d8c778023c99730025a78a09d1d716b0619d5",
        "6d844d94322c17c02349e9780f59398ef61107ca2dd1b8947c676ba83d6898f0",
        "4cdce331118195f94837de03be4faffe70e3fadd",
    ),
    "docs/research-completion-2026-09-22/verification/native-python-and-v2.log": (
        "f923ef4fa6357b422b15a6a4a443e63f3e4efd0b86de07f525bc65838362a6d4",
        "77e0b2cd4c933e48864be7d706887e328c83194db24f5775c1c611f932dfe7f2",
        "85a3f303a3ed27a2359933eaeffbe351f77be082",
    ),
}
TRANSFORM_FOR_PATH = {
    name: (
        "pytest_temp_username_to_<REDACTED_USER>"
        if name.endswith("case-08.pytest.stdout.log")
        else "absolute_home_path_to_<REDACTED_HOME>"
    )
    for name in DERIVATIVE_PATHS
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
FINAL_CASES = (
    (
        "scripts.run_completion_matrix",
        "docs/research-completion-2026-09-22/raw/attempt-20260922T220129Z-1790114489061895000",
        "docs/research-completion-2026-09-22/source-snapshots/python-final-instrumented-71e08e7eb067.json",
    ),
    (
        "scripts.run_typescript_guarded_matrix",
        "docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T220151Z-1790114511892918000",
        "docs/research-completion-2026-09-22/source-snapshots/typescript-v2-final-locked-8361f25baa0b.json",
    ),
)


def _safe_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise ValueError(f"unsafe path: {raw!r}")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in raw.split("/")):
        raise ValueError(f"unsafe path: {raw!r}")
    if path.as_posix() != raw or raw == MANIFEST or raw.startswith(".git/"):
        raise ValueError(f"unsafe or reserved path: {raw!r}")
    return raw


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _check_collisions(names: set[str]) -> None:
    portable: set[str] = set()
    for name in names:
        folded = unicodedata.normalize("NFC", name).casefold()
        if folded in portable:
            raise ValueError(f"case/Unicode path collision: {name}")
        portable.add(folded)


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def verify_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve(strict=True)
    manifest_path = root / MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("missing or linked EXPORT-MANIFEST.json")
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object
    )
    if manifest.get("format") not in {
        "tracked-source-export-v1",
        "public-source-export-v2",
        "public-source-export-v3",
    }:
        raise ValueError("unsupported export manifest format")
    public_source = manifest["format"] == "public-source-export-v3"
    if public_source:
        if manifest.get("source_kind") != "already_public":
            raise ValueError("invalid public source kind")
        origin_commit = manifest.get("origin_private_commit")
        if origin_commit is not None and (
            not isinstance(origin_commit, str) or not HEX40.fullmatch(origin_commit)
        ):
            raise ValueError("invalid private origin commit")
    if not isinstance(manifest.get("source_commit"), str) or not HEX40.fullmatch(
        manifest["source_commit"]
    ):
        raise ValueError("invalid source commit")
    entries = manifest.get("files")
    if (
        not isinstance(entries, list)
        or type(manifest.get("exported_file_count")) is not int
        or manifest["exported_file_count"] != len(entries)
    ):
        raise ValueError("exported file count mismatch")
    omission = [{"path": MANIFEST, "reason": "superseded_tracked_manifest"}]
    if (
        manifest.get("omissions") not in ([[], omission] if public_source else [[]])
        or type(manifest.get("omitted_file_count")) is not int
        or manifest["omitted_file_count"] != len(manifest["omissions"])
    ):
        raise ValueError("unexpected source omissions")
    if (
        type(manifest.get("tracked_source_file_count")) is not int
        or manifest["tracked_source_file_count"] != len(entries) + manifest["omitted_file_count"]
    ):
        raise ValueError("tracked source count mismatch")
    declared: dict[str, dict[str, Any]] = {}
    derivatives: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("non-object manifest entry")
        name = _safe_path(entry.get("path"))
        if name in declared:
            raise ValueError(f"duplicate path: {name}")
        mode = entry.get("git_mode")
        if mode not in {"100644", "100755"}:
            raise ValueError(f"unsupported mode for {name}: {mode!r}")
        for field, pattern in (
            ("exported_sha256", HEX64),
            ("original_sha256", HEX64),
            ("git_blob_sha1", HEX40),
        ):
            value = entry.get(field)
            if not isinstance(value, str) or not pattern.fullmatch(value):
                raise ValueError(f"invalid {field} for {name}")
        status = entry.get("status")
        transforms = entry.get("transforms")
        if status == "byte_identical":
            if entry["original_sha256"] != entry["exported_sha256"] or transforms != []:
                raise ValueError(f"invalid byte-identical assertion: {name}")
            if public_source and name in DERIVATIVE_PATHS:
                raise ValueError(f"lost derivative provenance: {name}")
        elif status == "retained_redacted_derivative" and public_source:
            expected = PUBLIC_DERIVATIVE_PROVENANCE.get(name)
            if expected is None or (
                entry["original_sha256"] != expected[0]
                or entry["exported_sha256"] != expected[0]
                or entry.get("private_origin_sha256") != expected[1]
                or entry.get("private_origin_git_blob_sha1") != expected[2]
                or transforms != []
            ):
                raise ValueError(f"invalid retained derivative provenance: {name}")
            derivatives.append(name)
        elif status == "redacted_derivative" and not public_source:
            if name not in DERIVATIVE_PATHS:
                raise ValueError(f"undeclared derivative path: {name}")
            if (
                entry["original_sha256"] == entry["exported_sha256"]
                or not isinstance(transforms, list)
                or not transforms
            ):
                raise ValueError(f"invalid derivative assertion: {name}")
            for transform in transforms:
                if (
                    not isinstance(transform, dict)
                    or transform.get("transform") != TRANSFORM_FOR_PATH[name]
                    or type(transform.get("occurrences")) is not int
                    or transform["occurrences"] <= 0
                    or not isinstance(transform.get("matched_prefix"), str)
                ):
                    raise ValueError(f"unsupported derivative transform: {name}")
            if not isinstance(entry.get("contract"), str) or not entry["contract"]:
                raise ValueError(f"derivative contract missing: {name}")
            derivatives.append(name)
        else:
            raise ValueError(f"unknown export status: {name}: {status!r}")
        declared[name] = entry
    if set(derivatives) != DERIVATIVE_PATHS:
        raise ValueError(
            f"derivative inventory mismatch: {sorted(set(derivatives) ^ DERIVATIVE_PATHS)}"
        )
    _check_collisions(set(declared) | {MANIFEST})

    actual: set[str] = set()
    actual_dirs: set[str] = set()
    for directory, dirs, files in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in dirs + files:
            path = base / name
            relative = path.relative_to(root).as_posix()
            info = path.lstat()
            if relative == ".git" or relative.startswith(".git/"):
                raise ValueError(f"Git metadata in export: {relative}")
            if stat.S_ISLNK(info.st_mode):
                raise ValueError(f"link in export: {relative}")
            if name in dirs:
                if not stat.S_ISDIR(info.st_mode):
                    raise ValueError(f"non-directory in export: {relative}")
                actual_dirs.add(relative)
            elif stat.S_ISREG(info.st_mode):
                actual.add(relative)
            else:
                raise ValueError(f"non-regular file in export: {relative}")
    _check_collisions(actual)
    expected = set(declared) | {MANIFEST}
    expected_dirs = {
        parent.as_posix()
        for name in expected
        for parent in PurePosixPath(name).parents
        if parent.as_posix() != "."
    }
    if actual_dirs != expected_dirs:
        raise ValueError(
            f"directory inventory mismatch: missing={sorted(expected_dirs - actual_dirs)}, extra={sorted(actual_dirs - expected_dirs)}"
        )
    _check_collisions(actual_dirs)
    missing, extra = sorted(expected - actual), sorted(actual - expected)
    if missing or extra:
        raise ValueError(f"file inventory mismatch: missing={missing}, extra={extra}")
    for name, entry in declared.items():
        path = root / name
        info = path.stat()
        expected_mode = 0o755 if entry["git_mode"] == "100755" else 0o644
        if stat.S_IMODE(info.st_mode) != expected_mode:
            raise ValueError(f"mode mismatch: {name}")
        if _digest(path) != entry["exported_sha256"]:
            raise ValueError(f"SHA-256 mismatch: {name}")
        if public_source:
            data = path.read_bytes()
            blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
            if blob != entry["git_blob_sha1"]:
                raise ValueError(f"public source Git blob mismatch: {name}")
    if stat.S_IMODE(manifest_path.stat().st_mode) != 0o644:
        raise ValueError("manifest mode mismatch")
    return {
        "files_verified": len(declared),
        "derivatives": derivatives,
        "manifest_sha256": _digest(manifest_path),
        "original_bytes_verified": False,
        "original_hash_limit": "Redacted private originals are absent; private SHA values are provenance assertions, not public-byte checks.",
    }


def verify_retained(root: Path) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for module, attempt, snapshot in FINAL_CASES:
        command = [
            sys.executable,
            "-m",
            "scripts.verify_source_snapshot",
            "--snapshot-manifest",
            snapshot,
            "--attempt",
            attempt,
        ]
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        run = subprocess.run(
            command, cwd=root, env=env, text=True, capture_output=True, check=False, timeout=120
        )
        if run.returncode:
            raise ValueError(
                f"retained verification failed: {' '.join(command)}\n{run.stdout}\n{run.stderr}"
            )
        results.append(
            {
                "module": module,
                "command": " ".join(command[1:]),
                "result": run.stdout.strip() or "pass",
            }
        )
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="extracted archive directory")
    parser.add_argument("--inventory-only", action="store_true", help="skip retained matrix replay")
    args = parser.parse_args()
    try:
        report = verify_inventory(args.root)
        if not args.inventory_only:
            report["retained"] = verify_retained(args.root.resolve())
        print(json.dumps(report, sort_keys=True, indent=2))
    except (OSError, TypeError, ValueError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        parser.exit(1, f"public export verification failed: {exc}\n")


if __name__ == "__main__":
    main()
