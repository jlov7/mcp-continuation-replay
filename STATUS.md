# Status

This repository is a research software preview. Its local synthetic checks and
retained evidence are described below; they do not establish production
reliability, independent replication, or hosted CI results for this revision.

## Local checkpoint, 2026-09-24

At this checkpoint, local source and native gates were reviewed. Hosted
validation had not been observed then. No upstream contact is claimed here.

## Interruption rollback engineering, 2026-09-24

Both outer `IssueStore` transaction scopes roll back the active SQLite
transaction on `BaseException` and re-raise the original signal. Fourteen
regression cases cover interruptions around issue creation and partial effects.
Their readback connections are closed explicitly.

At source commit `b97d842fb71935dc8b065f7a75f231d32d9377bb`, the full
`--verify-pinned-findings` gate passed 172 tests on each of local Linux ARM
Python 3.11 and 3.13, with 90.04% combined coverage against the 75% floor.
Neither final run reported warnings. The source distribution passed readback
of all 102 retained SQLite snapshots. These are local engineering results;
hosted CI, production effects, and public behavior were not established by
them.

## Historical runtime gate observed at 2026-09-23 source commit

At source commit `4696007f475061db1d7e258e7bfe881d1f8c800c`, the final native
runtime gate passed 158 tests in the Python/TypeScript v2 suite on each of macOS
Python 3.11 and 3.13, with 89.75% coverage against the unchanged 75% gate. Node
22.23.2 checks also passed.
These results are retained runtime evidence for that source commit. The current
README and status documentation changes inherit this evidence through unchanged
runtime files; no runtime suite was rerun for this documentation-only increment.

## 2026-09-23 additive continuation increment

That increment added [status-only result recovery](docs/RECOVERY-AND-TRANSPORT.md),
a hard exit after the first durable partial commit, structured status scope,
portable vectors, a two-principal test HTTP adapter, a native TypeScript
SQLite store, and three real loopback intermediary faults. These are additive
engineering checks designed after the frozen twelve-case studies. The new
tests exercise physical rows and raw transport behavior where applicable.
The TypeScript store is separately implemented but same-author; the HTTP
identity verifier uses public test tokens. Neither extends the historical
claim to production effects or real authentication. Failed and amended
attempts are retained in the local evidence. Exact source commits and gate
outputs identify the runs described here.

A post-result adversarial check found that the native store accepted changed
title/body when its caller reused a stale fingerprint. The local pre-fix
SQLite database and request/response record are retained separately. The
native store now checks persisted title/body alongside the fingerprint, and
the CLI validates the operation and consumed JSON fields before dispatch.
This is a later engineering correction; it does not change the frozen F
protocol or historical outcome. See the amendment in
`docs/RECOVERY-AND-TRANSPORT.md`.

## 2026-09-23 public-readiness implementation

Local source-candidate work adds a history-free export builder/verifier,
case-03 guided recovery, trust-boundary map, CI/stewardship files and
an additive precommit/SQLite-busy fault lab. The original twelve numbered
cases and their historical attempts remain intact. At that earlier checkpoint,
the full gate passed 136 Python/TypeScript v2 tests on macOS Python 3.11.16 and
3.13.15 with Node 22.23.2, including both new TS bridge cut points. This
historical checkpoint was superseded by the later 158-test gate described above.
The legacy TypeScript adapter passed 11 tests. Ruff, pyright, wheel/sdist build and fresh
installed CLI smoke passed. The two final retained 12/12 matrices verify via
their exact historical source snapshots; direct current-source hash checks
correctly reject changed implementation bytes.

Local history-free archive generation and readback completed at that checkpoint.
An external archive receipt, hosted CI, and a verified private security-reporting
route were unobserved there. These results do not support an upstream message
or a production exactly-once claim. See `docs/PUBLIC-VERIFICATION.md`,
`SECURITY-AND-ASSUMPTIONS.md` and `docs/FAULT-LAB.md` for scope.

**State:** local bounded research and engineering complete. The final guarded
Python and TypeScript v2 stdio attempts each requested, executed, and passed
all twelve frozen cases. No upstream contact is claimed.

The [frozen Python protocol](docs/research-completion-2026-09-22/PROTOCOL.md)
predated its first result run. The separate
[TypeScript v2 protocol](docs/research-completion-2026-09-22/typescript-v2/PROTOCOL.md)
was frozen before the TypeScript matrix. Their final retained evidence is the
[Python matrix](docs/research-completion-2026-09-22/raw/attempt-20260922T220129Z-1790114489061895000/SUMMARY.json)
and [TypeScript v2 matrix](docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T220151Z-1790114511892918000/SUMMARY.json).
Each verifier re-reads raw stdio replies and physical SQLite state, checks the
declared per-case mechanism, and requires a complete twelve-cell inventory.
The [source snapshots](docs/research-completion-2026-09-22/source-snapshots/README.md)
allow these and earlier passing attempts to verify without Git history.

The pinned Python `mcp==2.2.0` unguarded fixture still demonstrates the exact
duplicate and changed-input effects when a server omits durable replay
mediation. The ten unsafe witness tests remain expected controls. MCP MRTR
assigns at-most-once enforcement to a server that requires it; the guarded
application supplies that duty with one SQLite operation/effect transaction,
an exact stored-result replay, changed-binding conflict, and read-only
authoritative reconciliation. Transport loss stays `unknown` until the exact
operation ledger settles it. A concurrent first-use SQLite bootstrap race was
found and corrected before the final attempts. The failed TypeScript machinery
attempt and the earlier passing attempts remain unchanged in the archive.

The original TypeScript fingerprint adapter remains pinned to
`@modelcontextprotocol/sdk@1.30.0`. A separate, isolated current v2 runtime is
locked to `@modelcontextprotocol/server@2.0.0`, `core@2.0.0`, and `zod@4.6.5`.
Its real SDK stdio server passed the twelve semantic cases through a narrow
Python subprocess bridge to the **same** SQLite `IssueStore`. This tests SDK
wire handling and that integration; it is not independent storage validation.
The TypeScript state codec signs synthetic state without encrypting it. Its
fixture accepts only the declared body response shape and rejects extra fields
before an effect.

The [native verification record](docs/research-completion-2026-09-22/verification/RESULT.md)
retains logs for 94 combined Python/v2 tests passing at 86.86% coverage, above
the unchanged 75% gate. The historical TypeScript adapter passed 11 tests;
ruff, pyright, isolated v2 install, package build, and fresh wheel install
smoke passed. An earlier run had 77 passing tests but failed coverage at 52.44%
because subprocess execution was unmeasured; that failure and the correction
remain documented. Hosted CI was updated to install and test the isolated v2
fixture, but has not been run in this local task.

This is same-author synthetic testing on one host and one SQLite backend. It
does not establish production authentication, distributed at-most-once effects,
client exactly-once semantics, or external replication. The original question
about server duty is addressed by the specification; no upstream message was
sent. Raw transcripts and databases use synthetic keys and identities. Five
historical files with local paths have disclosed redacted derivatives in the
public-source export; see `docs/PUBLIC-VERIFICATION.md`.
