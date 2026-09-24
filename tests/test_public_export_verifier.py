"""Public inventory gate must fail on changed or undeclared distributed bytes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.verify_public_export import DERIVATIVE_PATHS, MANIFEST, verify_inventory


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fixture(root: Path) -> dict:
    files = []
    for name in sorted(DERIVATIVE_PATHS | {"README.md"}):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = f"exported {name}\n".encode()
        path.write_bytes(data)
        path.chmod(0o644)
        derivative = name in DERIVATIVE_PATHS
        files.append(
            {
                "path": name,
                "git_mode": "100644",
                "git_blob_sha1": "a" * 40,
                "original_sha256": "b" * 64 if derivative else _digest(data),
                "exported_sha256": _digest(data),
                "status": "redacted_derivative" if derivative else "byte_identical",
                "transforms": (
                    [
                        {
                            "transform": "pytest_temp_username_to_<REDACTED_USER>"
                            if name.endswith("case-08.pytest.stdout.log")
                            else "absolute_home_path_to_<REDACTED_HOME>",
                            "matched_prefix": "synthetic",
                            "occurrences": 1,
                        }
                    ]
                    if derivative
                    else []
                ),
                **({"contract": "synthetic original unavailable"} if derivative else {}),
            }
        )
    manifest = {
        "format": "public-source-export-v2",
        "source_commit": "c" * 40,
        "files": files,
        "exported_file_count": len(files),
        "tracked_source_file_count": len(files),
        "omitted_file_count": 0,
        "omissions": [],
    }
    (root / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_clean_public_inventory_passes(tmp_path: Path) -> None:
    manifest = _fixture(tmp_path)
    result = verify_inventory(tmp_path)
    assert result["files_verified"] == len(manifest["files"])
    assert result["original_bytes_verified"] is False


@pytest.mark.parametrize(
    "mutation",
    [
        "ordinary",
        "redaction",
        "missing",
        "extra",
        "emptydir",
        "casecollision",
        "symlink",
        "mode",
        "unsafe",
        "duplicate",
    ],
)
def test_public_inventory_rejects_mutation(tmp_path: Path, mutation: str) -> None:
    manifest = _fixture(tmp_path)
    derivative = tmp_path / min(DERIVATIVE_PATHS)
    if mutation == "ordinary":
        (tmp_path / "README.md").write_text("changed", encoding="utf-8")
    elif mutation == "redaction":
        derivative.write_text("changed", encoding="utf-8")
    elif mutation == "missing":
        derivative.unlink()
    elif mutation == "extra":
        (tmp_path / "extra.txt").write_text("undeclared", encoding="utf-8")
    elif mutation == "emptydir":
        (tmp_path / "undeclared").mkdir()
    elif mutation == "casecollision":
        (tmp_path / "readme.md").write_text("collision", encoding="utf-8")
    elif mutation == "symlink":
        derivative.unlink()
        derivative.symlink_to(tmp_path / "README.md")
    elif mutation == "mode":
        derivative.chmod(0o755)
    elif mutation == "unsafe":
        manifest["files"][0]["path"] = "../escape"
        (tmp_path / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
    else:
        (tmp_path / MANIFEST).write_text('{"format":"x","format":"y"}', encoding="utf-8")
    with pytest.raises(ValueError):
        verify_inventory(tmp_path)
