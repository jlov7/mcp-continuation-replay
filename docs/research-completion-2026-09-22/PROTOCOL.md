# Frozen completion protocol

**Protocol status:** frozen before result-bearing execution.  
**Date:** 2026-09-22.  
**Scope:** one local SQLite backend, synthetic server-configured principals, raw
stdio JSON-RPC, and the pinned MCP 2026-07-28 Python implementation.

This protocol closes the twelve semantic cases in `research/PROTOCOL.md`. It
does not test exactly-once effects in general, production authentication,
distributed databases, or independent implementations. The guarded server is
an application-level example of the durable server enforcement required by the
MCP MRTR specification.

## Frozen system boundary

The guarded tool accepts `operation_id`, `title`, and a bounded `mode`. The
principal, backend identifier, state-protection key, and fingerprint key come
from server configuration and cannot be asserted in tool arguments. The first
round returns SDK-sealed state containing a fresh issuance nonce, operation id,
issue time, and authority expiry. On the continuation round the SDK verifies
the state envelope before the handler sees its plaintext.

Before any effect, the application computes a keyed fingerprint over:

1. the configured principal;
2. tool identifier and version;
3. all tool arguments;
4. the verified plaintext continuation state; and
5. the accepted input responses.

The SQLite operation ledger stores the operation id, configured principal,
persisted backend id, fingerprint, issued time, authority expiry, state, effect
id, and stored result. The ledger binding and the normal issue effect commit in
one `BEGIN IMMEDIATE` transaction. Identical attempts return the stored result.
Any changed binding conflicts before another effect. Applied and partial rows
are retained as tombstones; expiry never turns an old operation id into a new
identity.

The harness passes only these guarded-server settings: `WIRE_SERVER_DB`,
`WIRE_BACKEND_ID`, `WIRE_PRINCIPAL`, `WIRE_CLOCK_EPOCH`,
`WIRE_AUTHORITY_TTL`, `WIRE_REPLAY_RETENTION_TTL`,
`WIRE_REQUEST_STATE_TTL`, `WIRE_STATE_KEY_HEX`,
`WIRE_FINGERPRINT_KEY_HEX`, and `WIRE_FAULT`. Child processes otherwise inherit
only the existing base allowlist used by the raw stdio client. Evidence records
key names and redacted presence markers, never key values or unrelated inherited
environment variables.

`ContinuationConsumer` never emits a retry action. A lost reply produces
`unknown` plus a read-only reconciliation action. Only an exact, authorized,
authoritative ledger observation can settle the result. A missing ledger,
diagnostic query, principal mismatch, backend mismatch, or expired authority
cannot authorize a new write.

## Time and concurrency controls

No case uses elapsed wall-clock sleeps to establish expiry. The guarded server
and read-back oracle receive an explicit integer Unix time from the harness.
Separate processes use the same fixed input time for normal cases. Expiry cases
restart the server at declared before/after times. Authority, application
replay retention, and SDK request-state TTL are distinct deadlines. Cases 7 and
10 choose their deadlines so the guard under test expires while the other two
remain current.

Case 8 uses two independent stdio server processes and two independent client
connections over one SQLite file. Both processes receive the same continuation
only after a harness barrier releases both worker threads. Completion is a
join, not a polling loop. SQLite `BEGIN IMMEDIATE` defines the bounded waiter
semantics for this experiment.

## Frozen twelve-case matrix

| Case | Guarded experiment | Required classification and evidence |
|---|---|---|
| 1 | Apply, then submit the identical continuation again. | Both replies carry the same stored result; one operation and one issue; second reply reports replay. |
| 2 | Mint state but never send the continuation; then reconcile. | No issue or ledger row; authoritative operation lookup is `unknown`; consumer action is `stop`, never retry. |
| 3 | Commit the continuation, suppress the reply, restart, then exercise the explicit identical-replay contract. | Initial consumer state is `unknown`; exact read-back is `applied`; replay returns stored result; one issue. |
| 4 | Reuse one operation id and state with changed `inputResponses`. | Application conflict before a second effect; one issue. |
| 5 | Mint two valid state tokens for the same operation and arguments; commit one, then submit the other. | Different issuance nonce changes the fingerprint; application conflict before a second effect. Tampering is separately rejected by the SDK boundary. |
| 6 | Commit under configured principal `alice`; attempt and reconcile under configured principal `bob`. | Attempt conflicts and Bob cannot obtain an authorized Alice observation; one issue. Principal is server configuration, not client metadata. |
| 7 | Commit while authority is current; while SDK state and replay retention remain valid, attempt the identical write and reconcile after authority expiry. | The application rejects the write for expired authority. Read-back may report the durable applied fact, but the consumer only returns the stored result and never gains fresh-write authority. |
| 8 | Release two independent processes/connections with the same continuation at one barrier. | Both receive the same logical result; exactly one reports first apply and one replay; one issue. |
| 9 | Hard-exit after the atomic commit and before writing the reply; restart and reconcile. | Transport outcome is `unknown`; exact ledger observation is `applied`; recovery returns the stored result without redispatch; one issue. |
| 10 | Apply before the application replay-retention deadline; while SDK state and authority remain valid, replay after retention. Then test the old token after SDK TTL and a fresh issuance with the old operation id. | The application explicitly rejects the otherwise valid post-retention replay and retains a tombstone. The SDK later rejects its expired token. Fresh issuance conflicts against the tombstone. No second effect or silent guarantee extension. |
| 11 | Send accepted `inputResponses` with `requestState` removed. | Guarded handler classifies the request as unsupported/rejected; no effect. A valid new round has neither field and still mints state. |
| 12 | In bounded multi-step mode, durably commit the issue, fail the watcher step, and durably record a separate failed compensation. Replay the same continuation. | Authoritative state is `partial`; issue and failed compensation remain; watcher is absent; replay never repeats the first effect. |

The existing unguarded cases remain controls. In particular, a blind retry
against the unmediated server and an unsafe fresh operation identity may create
duplicates. They are not counted as guarded conformance.

## Requested, executed, and reported inventory

The immutable input file `matrix-spec.json` is the requested inventory. The
runner must emit exactly one record for every requested case and no unrequested
case. Each record includes the case id, status (`pass`, `fail`, `unsupported`,
or `machinery_error`), expected classification, observed facts, process exit
codes, and transcript paths. The run is acceptable only when:

- the requested and executed case-id sets are exactly equal;
- every supported case passes its declared predicate;
- unsupported cells name the missing API or observation surface;
- any machinery error fails the run;
- raw JSONL, transcripts, SQLite snapshots, environment allowlist, commands,
  package versions, source hashes, and a derived Markdown table are retained;
- retained pre-audit evidence hashes remain unchanged.

Current released Python and TypeScript SDK capability probes are a separate
inventory. A cell is added to the behavioral matrix only when the released SDK
exposes a comparable 2026-07-28 MRTR surface and the same case can be executed
without changing this protocol. Otherwise the capability result is
`unsupported` with primary-source and installed-package provenance.

## Stop rules and claim ceiling

The matrix is finite at twelve semantic cases. Variants such as tampering and
fresh issuance are evidence within a case, not extra cases. No result changes
the normative conclusion that at-most-once enforcement is an application duty.
No public or upstream action follows from a local pass. Synthetic identities,
SQLite serialization, same-author adapters, and one host remain explicit
limits.
