"""Export path screening uses metadata before any archive content is read."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.build_public_export import ROOT, _blocked_path, _redact, detect_source_kind
from scripts.verify_public_export import MANIFEST, PUBLIC_DERIVATIVE_PROVENANCE


@pytest.mark.parametrize(
    "name",
    [
        ".env",
        ".env.local",
        "config/.env.production",
        ".secrets/token",
        "credentials/key.json",
        ".npmrc",
        ".pypirc",
        ".netrc",
        ".git-credentials",
        ".ssh/id_rsa",
        ".aws/config",
        ".gnupg/pubring.kbx",
        "nested/id_ed25519",
        "tls/server.pem",
        "cert/client.p12",
        "cert/client.pfx",
        "cert/private.key",
        "node_modules/lib/file.js",
    ],
)
def test_blocks_sensitive_filename(name: str) -> None:
    assert _blocked_path(name)


@pytest.mark.parametrize(
    "name", ["README.md", "reference/backend.py", "docs/evidence.json", "tests/test_cli.py"]
)
def test_allows_ordinary_source_filename(name: str) -> None:
    assert not _blocked_path(name)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _commit(root: Path, message: str) -> None:
    _git(root, "add", "-f", ".")
    subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Local Test",
            "-c",
            "user.email=local@example.invalid",
            "commit",
            "-qm",
            message,
        ],
        check=True,
        capture_output=True,
    )


def _build(root: Path, destination: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.pop("PYTHONPATH", None)
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "scripts.build_public_export",
            "--source-kind",
            "already-public",
            str(destination),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_public_git_reexport_preserves_origin_and_rejects_derivative_tamper(tmp_path: Path) -> None:
    seed = tmp_path / "seed"
    (seed / "scripts").mkdir(parents=True)
    for name in ("build_public_export.py", "verify_public_export.py"):
        shutil.copy2(ROOT / "scripts" / name, seed / "scripts" / name)
    (seed / "README.md").write_text("Public source\n", encoding="utf-8")
    for name, hashes in PUBLIC_DERIVATIVE_PROVENANCE.items():
        source = (ROOT / name).read_bytes()
        public = (
            source if hashlib.sha256(source).hexdigest() == hashes[0] else _redact(name, source)[0]
        )
        assert hashlib.sha256(public).hexdigest() == hashes[0]
        target = seed / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(public)
    (seed / MANIFEST).write_text(
        json.dumps({"format": "public-source-export-v2", "source_commit": "a" * 40}),
        encoding="utf-8",
    )
    _git(seed, "init", "-q")
    _commit(seed, "test: seed already-public source")
    assert detect_source_kind(seed) == "already-public"
    first = _build(seed, tmp_path / "out-one")
    assert first.returncode == 0, first.stderr
    first_root = Path(json.loads(first.stdout)["extracted_root"])
    first_manifest = json.loads((first_root / MANIFEST).read_text())
    assert first_manifest["origin_private_commit"] == "a" * 40
    assert first_manifest["omissions"] == [
        {"path": MANIFEST, "reason": "superseded_tracked_manifest"}
    ]

    next_seed = tmp_path / "next-seed"
    shutil.copytree(first_root, next_seed)
    _git(next_seed, "init", "-q")
    (next_seed / "README.md").write_text("Public source\nReviewed edit\n", encoding="utf-8")
    _commit(next_seed, "docs: revise public readme")
    second = _build(next_seed, tmp_path / "out-two")
    assert second.returncode == 0, second.stderr
    second_manifest = json.loads(
        (Path(json.loads(second.stdout)["extracted_root"]) / MANIFEST).read_text()
    )
    assert second_manifest["origin_private_commit"] == "a" * 40
    assert second_manifest["source_commit"] != first_manifest["source_commit"]
    assert (
        next(e for e in second_manifest["files"] if e["path"] == "README.md")["original_sha256"]
        == hashlib.sha256((next_seed / "README.md").read_bytes()).hexdigest()
    )

    _git(next_seed, "rm", "-q", MANIFEST)
    _commit(next_seed, "test: omit prior manifest")
    no_manifest = _build(next_seed, tmp_path / "out-no-manifest")
    assert no_manifest.returncode == 0, no_manifest.stderr
    no_manifest_data = json.loads(
        (Path(json.loads(no_manifest.stdout)["extracted_root"]) / MANIFEST).read_text()
    )
    assert no_manifest_data["origin_private_commit"] is None
    assert no_manifest_data["omissions"] == []

    derivative = next(iter(PUBLIC_DERIVATIVE_PROVENANCE))
    (next_seed / derivative).write_bytes((next_seed / derivative).read_bytes() + b"tamper")
    _commit(next_seed, "test: tamper derivative")
    with pytest.raises(ValueError, match="mixed private and public"):
        detect_source_kind(next_seed)
    rejected = _build(next_seed, tmp_path / "out-tamper")
    assert rejected.returncode != 0
    assert "approved public derivative changed" in rejected.stderr
