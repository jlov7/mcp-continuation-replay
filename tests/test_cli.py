from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from continuation_replay.cli import KEY_ENV

TEST_KEY = b"test-only-cross-language-key-32b"
ROOT = Path(__file__).resolve().parents[1]


def _run(
    *args: str, input_text: str = "", with_key: bool = True
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    if with_key:
        env[KEY_ENV] = TEST_KEY.hex()
    else:
        env.pop(KEY_ENV, None)
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "continuation_replay.cli", *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def test_cli_version() -> None:
    result = _run("--version", with_key=False)
    assert result.returncode == 0
    assert result.stdout.strip() == "0.0.1"


def test_cli_fingerprints_jsonl() -> None:
    request = {
        "principal": "alice",
        "tool_id": "create_issue",
        "tool_version": "1",
        "arguments": {"title": "spec"},
    }
    result = _run(input_text=json.dumps(request) + "\n")
    assert result.returncode == 0
    assert len(result.stdout.strip()) == 64
    assert result.stderr == ""


def test_cli_fails_closed_without_key() -> None:
    result = _run(input_text="{}\n", with_key=False)
    assert result.returncode == 2
    assert KEY_ENV in result.stderr
