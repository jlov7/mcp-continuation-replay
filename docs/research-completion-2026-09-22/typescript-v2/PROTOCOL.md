# Frozen additive TypeScript v2 guarded stdio protocol

Status: frozen before the TypeScript guarded result run, 2026-09-22. This is
additive to the immutable Python matrix at source commit
`3db5a1d551c0000c1288adb71cbf22bab2816c2c`; it does not reinterpret or
modify that run. `inventory.json` requests the same twelve semantic cases.

The released `@modelcontextprotocol/server@2.0.0` and
`@modelcontextprotocol/core@2.0.0` expose the MCP 2026-07-28 MRTR input and
signed request-state APIs. The guarded TypeScript server uses their real stdio
transport, `createRequestStateCodec`, and verified continuation accessor.
Unlike the Python SDK's encrypted state envelope, this SDK codec signs but does
not encrypt the payload. The state contains only synthetic operation identity,
nonce, and injected timestamps. Configured synthetic principal and backend id
are not client arguments. A fixed synthetic test key is reused across server
processes; no live key material is involved.

The application backend is deliberately shared with the Python reference:
one narrow JSON subprocess bridge invokes the existing `IssueStore` and
`ReadBack` over SQLite. The TypeScript work tests SDK wire handling and the
composition with this bridge; it does **not** independently validate the
storage algorithm or cross-implementation agreement. The bridge accepts only
`apply` and `status` operations, validates field types, and receives the
server-configured principal, backend, clock and keys through an allowlisted
environment. Its fingerprint binds principal, tool/version, arguments,
verified plaintext state, and accepted response. The ledger still controls
at-most-once dispatch and tombstones. The TypeScript server crashes with exit
70 after the bridge commits for the declared fault cases.

The fixture accepts exactly one `body` input response with `action: "accept"`,
`content: {"body": <string>}`, and either absent or null `_meta`. Extra
response, content, or metadata fields are rejected before an effect; they are
never discarded while constructing the fingerprint input. This is the
supported fixture schema, not a claim that MRTR prohibits richer responses.

All times use the same `matrix-spec.json` epochs and distinct deadlines.
The TypeScript process patches `Date.now` to the injected integer epoch before
it creates or verifies SDK state; the bridge receives the same epoch. No wall
sleep establishes expiry. Case 8 releases two independent Node stdio server
processes and their independent Python bridge invocations at one barrier. The
Python `BEGIN IMMEDIATE` SQLite transaction serializes effects. The same
`ContinuationConsumer` settles transport loss only from an exact status tool
observation. Authority expiry never grants a fresh write.

For each requested id 01–12 the runner retains a result status (`pass`,
`fail`, `unsupported`, or `machinery_error`), raw stdio transcripts, process
codes, SQLite snapshot, independent database facts, source/package hashes,
SDK version, command, and derived table. Unsupported requires a demonstrated
missing SDK API or unobservable boundary, not absence of local implementation.
The verifier requires exactly one result per requested case, re-reads the raw
transcripts and database, checks each semantic predicate, and fails on a
machinery error. The Python twelve-case receipt remains unchanged.

The claim ceiling is a synthetic, same-author, same-backend local comparison.
Passing cases do not establish production authentication, a distributed
ledger, general exactly-once effects, or client exactly-once behavior.
