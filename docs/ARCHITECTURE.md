# Architecture and trust boundaries

This is a reference application around MCP multi-round trip requests (MRTR), not a replacement protocol. The SDK carries a signed `requestState` continuation. The application decides whether that continuation may produce a new effect. The [lost-reply walkthrough](RECOVERY-WALKTHROUGH.md) gives one runnable path through the components.

## Boundaries

1. **Wire and continuation.** `reference/guarded_server_stdio.py` uses the pinned Python SDK for `input_required` and continuation transport. `reference/typescript_guarded_server.cjs` exercises the TypeScript v2 SDK. Neither SDK alone supplies the application's durable operation ledger.
2. **Equivalence and authority.** `src/continuation_replay/fingerprint.py` and `adapters/typescript/src/fingerprint.ts` implement the same keyed canonicalization contract. The guarded server uses an operation ID, configured synthetic principal, persisted backend ID, and request fingerprint to decide whether a retry matches. The TypeScript v2 fixture calls `reference/typescript_guarded_bridge.py` for the same backend behavior; it is not a second store implementation.
3. **Effect and record.** `reference/backend.py` writes the operation record and synthetic issue in one SQLite transaction. A matching retry retrieves the stored result. Changed inputs conflict before a second dispatch. A retained expired identity rejects reuse. This atomicity applies to this database transaction; an external service would need an equivalent boundary.
4. **Observation and consumer.** `reference/readback.py` creates operation status observations; `reference/consumer.py` keeps a lost transport reply `unknown` until an authoritative observation matches operation ID, principal, backend and structured `scopeBinding`. Free-text `scope` explains the read. A terminal applied status carries a stored result consistent with the physical effect ID; the consumer returns it without redispatch. A partial result is diagnostic and cannot become applied success. An absent or unfinished ledger stays `unknown`. `observedAt` records time but is not compared with the attempt clock: an older immutable terminal observation may remain valid, while an `unknown` observation does not settle future state. Status never authorizes a fresh write.

The additive `reference/loopback_http.py` wraps the released Python SDK modern
HTTP handler with a fixed two-token test verifier. It chooses a principal for
each request; the transport does not provide production authentication. The
native TypeScript store in `adapters/typescript/src/native_store.ts` uses Node
SQLite and its own transitions. The existing TypeScript v2 SDK fixture still
uses the Python bridge. `reference/loopback_proxy.py` records both sides of
three loopback HTTP faults. See [recovery and transport checks](RECOVERY-AND-TRANSPORT.md)
and the [predeclared protocol](TRANSPORT-STUDY-PROTOCOL.md).

The trusted server supplies principal and backend identity; user-controlled wire arguments do not choose them. This fixture does not implement real authentication. Request-state expiry, operation authority, and replay retention are distinct checks. The TypeScript v2 state codec signs synthetic state without encrypting it. A fingerprint key must be provisioned by a caller and kept private; a digest can still reveal repeated input.

## Cases that test the design

| Case | Mechanism under test | What settles it |
|---|---|---|
| 03 | Commit, then server exit before reply | Same-identity status and stored-result replay; one physical issue row |
| 04–05 | Changed inputs or stripped state | Conflict or rejection before a new effect |
| 07 and 10 | Authority and retention expiry | Separate rejection at each boundary |
| 08 | Concurrent first use | One first apply and one replay |
| 09 | Crash recovery without redispatch | Read-only operation status |
| 12 | Partial effect and failed compensation | Original effect and separate compensation event remain visible |

The [frozen protocols and raw matrices](REPOSITORY-GUIDE.md) define all twelve requested cases and bind their observations to exact source snapshots. [Current findings](../research/CURRENT-FINDINGS.md) explain why the unguarded duplicate-effect control is expected under MCP's server-duty language. [Security assumptions](../SECURITY-AND-ASSUMPTIONS.md) state what would need to change for a real backend.
