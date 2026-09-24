# Current findings — 2026-09-22 local completion

This document gives the current interpretation of the retained local studies.

## Normative source result

The MCP 2026-07-28 MRTR server requirements state that request-state bindings
do not guarantee single use and that a server requiring at-most-once semantics
must enforce this server-side. The AAI Foundation design note on
`requestState` likewise describes replay policy as a distinct layer using a
nonce/redemption record and durable state.

Primary sources checked for this audit:

- MCP MRTR pattern, server requirements item 5:
  <https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr>
- AAI Foundation, “Designing requestState for Multi-Round Trip Requests,”
  2026-08-12: <https://aaif.io/blog/designing-requeststate-for-multi-round-trip-requests>
- MCP PR #3182, closed 2026-08-23; its author explicitly excluded MRTR
  continuation equivalence from that proposal.
- MCP PR #3312, open at the audit date; adjacent failure-classification work,
  not effect reconciliation.

## What the experiment establishes

On the pinned Python SDK `mcp==2.2.0`, a deliberately non-idempotent server with
no redemption ledger dispatches duplicate identical continuations, changed
input responses, and stripped-state continuations. A crash after commit followed
by blind replay also creates a second record. These exact observations are
preserved as witness tests at both in-process and raw stdio layers where stated.

This is expected when a server omits the at-most-once mechanism that the
specification assigns to it. It is not evidence that `RequestStateBoundary` is
defective: that boundary provides integrity, expiry, audience, principal, and
request binding; it does not claim durable redemption.

## Reference behavior added by the audit

The reference service supplies the missing server-side duty within a narrow
SQLite model. It stores the operation binding and effect in one immediate
transaction, returns the stored result for an identical retry, and rejects
changed bindings before dispatch. The persisted backend id and configured
principal constrain reconciliation.

Transport failure remains `unknown`. A title/body query may show diagnostic row
presence, but it is not authoritative operation reconciliation. Only the exact
operation ledger can settle the reference consumer, and a missing ledger row is
still `unknown` because absence alone is not terminal non-application proof.

## Frozen guarded stdio result

The protocol was frozen at `a529c959f990520857f5644b21e4ff2531bed7c9`
before the new run. The guarded implementation at
`3db5a1d551c0000c1288adb71cbf22bab2816c2c` passed all twelve requested
wire cases. The retained verifier re-read raw JSON-RPC transcripts and SQLite
snapshots, checked exactly one record per requested case, and confirmed the
declared response mechanisms against independent database state. Lost replies
and hard exits remained `unknown` until a restarted server returned an exact
operation-ledger observation. Expired authority and retention each rejected a
write under distinct live SDK-state timing. Concurrent separate processes
produced one first apply and one stored replay. The partial case retained the
issue, absent watcher, failed compensation and four durable step events.

Two simultaneous first-use SQLite constructors later exposed a separate schema
bootstrap race in the shared backend. The backend now holds one immediate
transaction across metadata insertion, backend-ID verification, and schema
creation. A simultaneous fresh-database regression passes, and competing
backend IDs leave one accepted binding and one rejected constructor. The
original Python attempt remains byte-for-byte retained and verifies against
its exact source commit. The final [Python attempt](../docs/research-completion-2026-09-22/raw/attempt-20260922T220129Z-1790114489061895000/SUMMARY.json)
again executed and passed all twelve frozen cells.

This is a same-author application reference on one local SQLite backend with
synthetic configured identities and an injected clock. It does not show that
the SDK supplies at-most-once effects by itself, that arbitrary backends are
safe, or that a consumer has exactly-once semantics. Original unguarded
duplicate-effect witnesses remain in the full gate as expected controls.

## TypeScript and fingerprint scope

`@modelcontextprotocol/sdk@1.30.0` is retained as the exact original pin and
does not expose the Python experiment's 2026-07-28 MRTR surface. This is a fact
about 1.30.0 only. A separate installed `@modelcontextprotocol/server@2.0.0`
and `core@2.0.0` probe confirmed one real raw stdio MRTR round trip and signed
request-state tamper rejection. The Python fixture pins `mcp==2.2.0`.
An additive, separately frozen
[TypeScript v2 protocol](../docs/research-completion-2026-09-22/typescript-v2/PROTOCOL.md)
then exercised the same twelve cases with the locked v2 SDK. Its
[locked-runtime attempt](../docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T220151Z-1790114511892918000/SUMMARY.json)
executed and passed 12/12. Its fixture also rejects response fields outside
the declared body-input schema before an effect. The Node server uses a narrow
Python subprocess bridge to the same `IssueStore` and `ReadBack`; this compares
SDK wire behavior and integration, not independently implemented persistence. The TypeScript
state codec signs but does not encrypt its synthetic payload.

The same-author Python and TypeScript fingerprint implementations test byte
parity under one explicit canonicalization. They do not constitute independent
validation. A caller must provide a secret HMAC key; the digest still reveals
equality. The accepted numeric domain is integral values within JavaScript's
safe range.

## Publication decision

The specification's server-duty language already addresses the original
ambiguity about single-use request state. Future work on
continuation-equivalence vectors or recovery ergonomics would require fresh
human analysis and current-source verification. No upstream acceptance is
claimed.
