"""The unsafe control — a retry with a NEW identity, demonstrating double execution.

Protocol §5: a deliberate baseline that retries with a new identity and
demonstrates duplicate execution. It exists to show the failure mode the safe
path prevents. It is a CONTROL — labelled, never shipped, never part of any
recommended recovery decision. If this test ever fails, the harness is broken.
"""

from __future__ import annotations

from reference.backend import IssueStore
from reference.readback import ReadBack

UNSAFE = True  # deliberate: this file encodes the unsafe baseline


def test_unsafe_new_identity_retry_duplicates_the_effect() -> None:
    """UNSAFE CONTROL: a fresh-identity retry after the same operation commits
    creates a SECOND effect. This baseline is what the safe path must prevent.
    """
    store = IssueStore(":memory:")
    try:
        rb = ReadBack(store)
        store.create_issue("spec", body="alpha")
        # Unsafe: retry as a NEW logical operation (fresh identity, no replay
        # authority check). The backend obligingly creates a second effect.
        store.create_issue("spec", body="alpha")
        observed = rb.observe_by_title("spec", operation_id="unsafe-control")
        assert observed.effects == 2, (
            f"unsafe control expects duplicate execution; got {observed.effects}"
        )
    finally:
        store.close()
