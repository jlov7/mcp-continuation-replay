"""Shared fixtures for the continuation-replay experiments.

Every harness import below was resolved by reading the pinned SDK at
`mcp==2.2.0`, not guessed. See `research/CURRENT-FINDINGS.md`.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from reference.backend import IssueStore
from reference.readback import ReadBack
from tests.wire_client import RawStdioClient

ROOT = Path(__file__).resolve().parents[1]

EXPECTED_PINNED_FINDINGS = {
    "tests/test_conformance_sweep.py::test_case_01_identical_retry_returns_the_same_logical_result": "duplicate_effect",
    "tests/test_conformance_sweep.py::test_case_03_reply_lost_replay_does_not_create_a_second_record": "duplicate_effect",
    "tests/test_conformance_sweep.py::test_case_04_changed_input_responses_conflicts_before_dispatch": "changed_input_dispatched",
    "tests/test_conformance_sweep.py::test_case_08_concurrent_identical_attempts_yield_one_effect": "duplicate_effect",
    "tests/test_conformance_sweep.py::test_case_11_stripped_metadata_is_not_false_conformance": "stripped_state_dispatched",
    "tests/test_replay_and_equivalence.py::test_replayed_token_must_not_duplicate_the_effect": "duplicate_effect",
    "tests/test_replay_and_equivalence.py::test_changed_input_responses_must_conflict_before_dispatch": "changed_input_dispatched",
    "tests/test_wire_fault_injection.py::test_case_09b_wire_crash_replay_does_not_create_second_record": "duplicate_effect_after_crash",
    "tests/test_wire_replay.py::test_wire_identical_retry_does_not_duplicate_the_effect": "duplicate_effect",
    "tests/test_wire_replay.py::test_wire_changed_input_responses_conflicts_before_dispatch": "changed_input_dispatched",
}
_EXECUTED_PINNED_FINDINGS: dict[str, str] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--verify-pinned-findings",
        action="store_true",
        help="require the complete exact pinned-finding witness inventory to execute and pass",
    )


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Fail collection if the exact pinned-finding inventory drifts."""
    if not items or not items[0].config.getoption("--verify-pinned-findings"):
        return
    actual: dict[str, str] = {}
    for item in items:
        marker = item.get_closest_marker("pinned_finding")
        if marker is not None:
            mechanism = marker.kwargs.get("mechanism")
            if not isinstance(mechanism, str):
                raise pytest.UsageError(f"{item.nodeid}: pinned_finding needs mechanism=<str>")
            actual[item.nodeid] = mechanism
    if actual != EXPECTED_PINNED_FINDINGS:
        missing = sorted(set(EXPECTED_PINNED_FINDINGS) - set(actual))
        unexpected = sorted(set(actual) - set(EXPECTED_PINNED_FINDINGS))
        changed = sorted(
            nodeid
            for nodeid in set(actual) & set(EXPECTED_PINNED_FINDINGS)
            if actual[nodeid] != EXPECTED_PINNED_FINDINGS[nodeid]
        )
        raise pytest.UsageError(
            f"pinned finding inventory drifted; missing={missing}, unexpected={unexpected}, "
            f"changed_mechanism={changed}"
        )


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    if report.when != "call":
        return
    mechanism = EXPECTED_PINNED_FINDINGS.get(report.nodeid)
    if mechanism is not None and report.passed and not hasattr(report, "wasxfail"):
        _EXECUTED_PINNED_FINDINGS[report.nodeid] = mechanism


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if not session.config.getoption("--verify-pinned-findings") or exitstatus != 0:
        return
    if _EXECUTED_PINNED_FINDINGS != EXPECTED_PINNED_FINDINGS:
        missing = sorted(set(EXPECTED_PINNED_FINDINGS) - set(_EXECUTED_PINNED_FINDINGS))
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"pinned finding execution incomplete; missing or non-passing={missing}", red=True
            )


@pytest.fixture
def anyio_backend() -> str:
    """The SDK's own suite runs under asyncio; match it."""
    return "asyncio"


@pytest.fixture
def store() -> Iterator[IssueStore]:
    s = IssueStore(":memory:", backend_id="sqlite:test")
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def readback(store: IssueStore) -> ReadBack:
    return ReadBack(store, principal="test-principal")


@pytest.fixture
def wire_client(tmp_path) -> Iterator[RawStdioClient]:
    """A fresh server subprocess and a transcript capturing every byte.

    The first request (`tools/list` with the modern envelope) decides the
    protocol era, so it must be sent before the test body runs — everything
    else would open a legacy-era connection where MRTR fails to serialize.

    Each test gets its own DB file (`tmp_path`), so no test ever deletes the
    server's database out from under it.
    """
    client = RawStdioClient(
        server_cmd=[sys.executable, str(ROOT / "reference" / "server_stdio.py")],
        transcript_path=tmp_path / "wire.transcript.log",
        db_path=tmp_path / "server.db",
    )
    try:
        client.open_connection()
    except Exception:
        client.close()
        raise
    try:
        yield client
    finally:
        client.close()
