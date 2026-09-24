# Final local verification record

The native gate was run against source commit
`921ad3db31b2662d12a6273ffe79d172053d8cae` on macOS with Python 3.13.15.
The [combined gate log](native-python-and-v2.log) records 94 passed and 86.86%
coverage, above the unchanged 75% minimum. The 94 comprise 77 native Python
tests and 17 additive TypeScript v2 wire/bridge tests. The measured set includes
`reference/guarded_server_stdio.py` at 83%, `reference/server_stdio.py` at 95%,
and `reference/typescript_guarded_bridge.py` at 87%; none was excluded to make
the threshold pass. The command was:

```bash
TS_V2_NODE_MODULES="$PWD/adapters/typescript-v2/node_modules" \
  .venv/bin/python -m pytest -q -p no:cacheprovider --verify-pinned-findings \
  tests typescript_v2_tests --cov=src --cov=reference --cov-report=term-missing
```

Before subprocess instrumentation, the 77 native Python tests passed but the
same 75% coverage gate failed at 52.44%. The test process did not collect
server subprocesses, and the three subprocess-only modules registered 0%.
This was a coverage machinery failure, not a passing native gate. That first
run's terminal output was not separately retained as a log. A later native-only
run with instrumentation passed 77 tests at 76.28%, but the retained combined
run above is the final, broader gate. Coverage now uses the supported
`subprocess` patch and parallel data files, forwards only the serialized
coverage config through the sanitized test processes, and loads the test-only
startup hook from `tests/coverage_startup/`. The hard-exit-70 fault can bypass
coverage flushing; its effect is instead checked by the retained raw wire and
SQLite evidence.

The independent tool logs record [ruff](ruff.log) clean, [pyright](pyright.log)
with zero errors, and the [historical TypeScript adapter](legacy-typescript.log)
at 11/11. The v2 SDK is isolated under `adapters/typescript-v2/`, preserving the
historical 1.30.0 adapter. An [offline fresh npm install](typescript-v2-install.log)
from its exact lock passed with three packages and zero reported vulnerabilities;
the installed server/core/zod module hashes match `typescript-v2/sdk-lock.json`.
The [focused additive v2 log](typescript-v2-focused.log) records 17/17. These
local checks do not claim hosted CI execution.

The [offline package build](package-build.log) produced an sdist with SHA-256
`63b876512ad0b41d9ff496d28fcf9a7d41e84a9d1548c535feeba1eab35c817a`
and a wheel with SHA-256
`1abb9e5bdaa8ab6a95c5c79b97cd0fdad0406c6cfdd09343fac9de4232d42623`.
The [fresh-install log](fresh-install.log) records a `--no-index --no-deps`
wheel install, the installed command version, and a synthetic keyed fingerprint
smoke. The first offline build attempt could not use the sandboxed default uv
cache; the successful run used the existing local cache with no network.

The frozen Python and TypeScript twelve-case raw matrices remain separate
research evidence. Their verifiers check transcripts and physical SQLite rows,
not coverage totals. The final [Python attempt](../raw/attempt-20260922T220129Z-1790114489061895000/SUMMARY.json)
and [TypeScript v2 attempt](../typescript-v2/raw/attempt-20260922T220151Z-1790114511892918000/SUMMARY.json)
each passed 12/12 from clean committed source after instrumentation and runtime
locking. Their exact history-free source snapshots are indexed in
[source-snapshots](../source-snapshots/README.md).
