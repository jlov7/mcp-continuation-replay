"""Start coverage only in explicitly instrumented wire-test children."""

from __future__ import annotations

import os

if os.environ.get("COVERAGE_PROCESS_CONFIG"):
    import coverage

    coverage.process_startup()
