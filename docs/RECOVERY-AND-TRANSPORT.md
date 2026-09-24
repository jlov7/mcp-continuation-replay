# Recovery contract and transport checks

This additive local increment lets a consumer recover the stored result after
a committed continuation loses its reply. The Python server exits after its
SQLite commit; a restarted server answers `get_operation_status`; the consumer
returns the stored value without calling the continuation again. The wire test
checks the restart transcript and reads the ledger and physical issue row.

The status parser requires matching operation ID, principal, backend and a
structured `scopeBinding`. The free-text `scope` remains diagnostic. An applied
status must contain a result consistent with its physical effect ID. A partial
status may carry its durable partial result but cannot be reported as applied.
An absent or unfinished record stays `unknown`, with no new write authorized.
`observedAt` is a timezone-aware audit timestamp. There is no wall-clock
freshness cutoff: an older observation of an immutable terminal record can
remain valid, while an `unknown` observation cannot settle an operation that
may later advance. The caller still has to trust and authorize the status
source; these fields are not a signed proof.

A separate hard-exit test stops immediately after the partial path's first
durable commit. Restart finds one issue, an `in_progress` ledger entry, no
watcher and no compensation. Status remains `unknown`; an attempted replay is
refused. An operator must inspect the operation row, issue, watcher,
compensation and event rows, then decide whether to finish, compensate under
a separate identity, or leave it unresolved. The fixture performs none of
those actions automatically.

The [versioned vectors](../research/portable-continuation-v1.json) and
[`run_portable_vectors.py`](../scripts/run_portable_vectors.py) give another
implementer a small challenge set. Changed accepted input under consumed
state illustrates a conditional server single-use duty; the exact conflict
response, fingerprint format, operation-ID binding, read-only recovery, and
new-issuance policy belong to this reference application. The runner exercises
the Python fingerprint and consumer. A planted implementation that ignores
accepted responses fails the fixed vector pack. This is a local adapter test,
not independent interoperability validation.

Three further bounded checks ran locally under the frozen
[protocol](TRANSPORT-STUDY-PROTOCOL.md):

| Check | Local observation | Limit |
| --- | --- | --- |
| Per-request identity | Two public test bearer contexts over the pinned Python SDK's loopback Streamable HTTP route could not read or replay each other's operation. | The outer token map and process are trusted; no production IdP or TLS was tested. |
| Native TypeScript store | A separate TypeScript transition implementation using Node SQLite passed lost-reply status, changed input, retention, absent status, and coordinated competing first use. Python read the physical SQLite tables independently. | Same author and SQL engine; no outside human replication. The native store is a bounded reference, not the TypeScript v2 SDK server's backend. |
| HTTP intermediary | A real loopback proxy dropped and delayed committed replies, and stripped state before dispatch. Both sides' request/response bytes and physical effects were retained. | Only the pinned Python SDK modern HTTP path and a local proxy were tested. |

Post-result engineering amendment (2026-09-23): an adversarial native-store
repro reused one caller-supplied fingerprint with a changed title or body.
The original store returned the prior result as a replay. Its SQLite database,
request/response record, and source hashes were retained in the local
coordinator evidence; the frozen F protocol and outcome were not rewritten.
The native store now compares the actual persisted title/body as well as the
fingerprint before replay. The CLI rejects unknown operations and malformed
identity or payload fields before dispatch. The fingerprint remains an opaque
caller-supplied binding for other continuation inputs; this store does not
parse a full MRTR request. New regression cases check both changed fields and
independently read the unchanged physical rows.

Run the portable pack with `python -m scripts.run_portable_vectors` after
installing the source dependencies. The new executable checks are
`tests/test_next_recovery.py`, `tests/test_portable_vectors.py`,
`tests/test_native_ts_store.py`, `tests/test_loopback_identity.py`, and
`tests/test_loopback_proxy.py`. Loopback tests require permission to bind
`127.0.0.1`; the native store needs a Node release with `node:sqlite` and
TypeScript stripping. These are local engineering tests added after the
historical matrices were visible. They do not expand those frozen results or
establish distributed exactly-once effects.
