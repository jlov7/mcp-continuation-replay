# Development and verification

Use a writable source checkout with Python 3.11 or 3.13 (the locally gated versions), `uv`, and Node 22. The package declares Python >=3.11; other versions were not part of the retained gate. The retained TypeScript v2 attempt used Node 22.23.2; use that version when comparing local results. The pinned Python SDK is `mcp==2.2.0`; the v2 fixture locks `@modelcontextprotocol/server@2.0.0`, `@modelcontextprotocol/core@2.0.0`, and `zod@4.6.5`. The original fingerprint-only TypeScript adapter pins `@modelcontextprotocol/sdk@1.30.0` and does not exercise MRTR.

The shortest live recovery check is in [the walkthrough](RECOVERY-WALKTHROUGH.md). For changes to implementation, tests, dependencies, or runtime configuration, run the current-source gates from repository root:

```bash
uv sync --locked --extra dev --python 3.13
uv run ruff check .
uv run ruff format --check reference/backend.py reference/guarded_server_stdio.py scripts/build_public_export.py scripts/demo_lost_reply.py scripts/run_fault_lab.py scripts/verify_public_export.py tests/test_fault_lab.py tests/test_fault_lab_runner.py tests/test_public_export_builder.py tests/test_public_export_verifier.py typescript_v2_tests/test_fault_lab_typescript.py
uv run pyright src reference scripts tests typescript_v2_tests
npm ci --prefix adapters/typescript-v2
TS_V2_NODE_MODULES="$PWD/adapters/typescript-v2/node_modules" \
  uv run pytest -q -p no:cacheprovider --verify-pinned-findings tests typescript_v2_tests \
  --cov=src --cov=reference --cov-report=term-missing
uv build
```

The full pytest gate requires all ten exact pinned-behavior witness tests and a 75% combined `src` / `reference` coverage floor. A focused test selection omits `--verify-pinned-findings`; that omission must not be reported as a full pass. A changed observed effect or machinery failure fails normally. Run the legacy TypeScript fingerprint adapter separately:

The [recovery and transport checks](RECOVERY-AND-TRANSPORT.md) are included
in the current full pytest gate. They bind two local HTTP ports and invoke
the native TypeScript store using `node:sqlite`; use Node 22.16 or later for
its [`DatabaseSync` timeout option](https://nodejs.org/download/release/v22.17.0/docs/api/sqlite.html). A `NATIVE_NODE` path can select a tested
local Node binary without changing the rest of the gate. The loopback client
records modern `Mcp-Method` and `Mcp-Name` headers as required by the pinned
SDK's HTTP route. The [frozen study protocol](TRANSPORT-STUDY-PROTOCOL.md)
lists the requested cells and failed amendments.

```bash
cd adapters/typescript
npm ci
npm test
```

On a Mac with `fnm`, `fnm exec --using 22.23.2 npm ci --prefix adapters/typescript-v2` can select the retained Node version for a command. Keep the same Node selection for the subsequent v2 pytest gate because it starts the Node server. The commands above otherwise assume Node 22 is already active. The v2 dependencies are installed independently from the legacy adapter.

## Historical evidence and source snapshots

These commands verify the retained final matrices against their **historical source snapshots**, using Python's standard library. They do not run the live SDK servers. The direct verifiers intentionally reject changed current implementation hashes:

```bash
python3 -B -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/python-final-instrumented-71e08e7eb067.json \
  --attempt docs/research-completion-2026-09-22/raw/attempt-20260922T220129Z-1790114489061895000
python3 -B -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/typescript-v2-final-locked-8361f25baa0b.json \
  --attempt docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T220151Z-1790114511892918000
```

For a pristine public source archive, run [public export verification](PUBLIC-VERIFICATION.md) before any installer or test. That verifier checks distributed bytes and both final retained matrices without SDK packages or Git history. Its private-origin v2 and already-public v3 paths have distinct provenance fields and must not be conflated.

For changes that touch a claimed behavior, add or update raw-wire assertions and independent physical readback. Keep output directories outside the checkout. See [the fault lab](FAULT-LAB.md) for named cut points. The retained verification logs are historical results, not pass claims for a later checkout. Hosted CI has not been observed for this revision.
