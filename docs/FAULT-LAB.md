# Additive fault and SDK regression lab

Version 1, 2026-09-23. These cases were added after the twelve-cell matrix was
exposed. They are engineering regression tests, not a blinded study or new
protocol result. The frozen twelve Python and TypeScript v2 cases and retained
attempts remain unchanged.

Run `uv run pytest -q -p no:cacheprovider tests/test_fault_lab.py
typescript_v2_tests/test_fault_lab_typescript.py` with `TS_V2_NODE_MODULES`
pointing to an isolated `npm ci` installation. Each precommit process is given
a synthetic clock and operation identity, follows the existing raw-wire case
helpers, and exits at a named callback inside the SQLite transaction. The
Python server exits before replying; the TypeScript server remains alive and
returns a machinery error after its Python bridge child exits. Tests require
the exact exit code or wire error, a real `input_required` round and
independent physical SQLite readback. No sleep or elapsed-time assertion
decides success; the wire client has an eight-second failure bound.

| Schedule | Expected observation | Current local result |
|---|---|---|
| Hard exit immediately after ledger insert, before issue insert | Python stdio exits 71; TS bridge child exits 71 and TS stdio returns a machinery error; zero committed rows in both; absent-ledger status remains `unknown` | Pass in both SDK fixtures |
| Hard exit after issue insert, before commit | Python stdio exits 72; TS bridge child exits 72 with a machinery error; zero committed rows in both | Pass in both SDK fixtures |
| SQLite writer lock held by another connection | Immediate `locked` error before dispatch; zero rows; same identity can later apply once and replay once | Pass |
| Exception after issue insert | Rollback leaves zero rows; a subsequent same-identity call applies once | Pass |

The existing case 03 is the opposite cut point: the transaction commits, the
server exits before reply, the consumer remains `unknown` until status readback,
and replay yields one physical effect. Case 08 covers concurrent first use;
case 12 covers a durable partial effect with failed compensation. The unsafe
changed-identity control in `tests/test_unsafe_control.py` creates two effects
by design.

The later [recovery and transport checks](RECOVERY-AND-TRANSPORT.md) add
`exit-after-partial-first-commit` as exit code 73. That cut occurs after the
issue and `in_progress` operation row commit, before watcher or compensation
attempt. `tests/test_next_recovery.py` restarts and sees one issue, one
unfinished operation, no watcher and no compensation. Status is `unknown`,
and replay is refused. An operator must read the physical rows and decide
on any further action under a separate authorized identity; this fixture
does not retry compensation.

For an auditable local attempt, run the following from a clean committed
checkout:

```bash
python -m scripts.run_fault_lab --output-dir OUTSIDE_SOURCE \
  --node-modules ABSOLUTE_V2_NODE_MODULES
```

`RESULT.json`
records exact package versions, source commit and dirty state, requested and
executed cells, failures, physical row counts and SHA-256 values for retained
wire transcripts, databases and test logs. The output directory must not
already exist. The seven requested cells include the deliberate unsafe control.
If the run times out or JUnit output is missing, the runner still writes a
failure `RESULT.json` with partial logs, artifact hashes, observed cells and
unknown outcomes for cells without a trustworthy result. It also records
source HEAD and dirty state before and after the invocation.

The Python wire fixture pins `mcp==2.2.0`. The TypeScript v2 guarded fixture
pins `@modelcontextprotocol/core@2.0.0`,
`@modelcontextprotocol/server@2.0.0` and `zod@4.6.5`, and uses the same Python
SQLite backend. The two new precommit exits ran through its subprocess bridge;
they observed a TS wire error while its Python bridge child exited. This is
cross-SDK integration over one store, not independent storage corroboration.
SQLite busy and exception rollback were exercised at the Python backend only.
The legacy TypeScript fingerprint adapter pins
`@modelcontextprotocol/sdk@1.30.0` and does not expose MRTR. No later SDK pair
has been measured. A future upgrade must record exact lockfiles, MRTR surface,
all requested cells including unsupported/failing cells, raw wire and physical
readback before a compatibility claim changes.
