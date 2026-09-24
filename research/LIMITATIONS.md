# Limitations

> Updated 2026-09-22. `CURRENT-FINDINGS.md` is the current interpretation.

The 2026-09-23 [recovery and transport checks](../docs/RECOVERY-AND-TRANSPORT.md) have their own
protocol and retained local evidence. Its status-only recovery assumes an
authorized, truthful status source and a durable SQLite ledger/effect pair.
The loopback bearer verifier is a test adapter, not real authentication. The
native TypeScript store reduces shared Python transition-code risk but uses
the same author and SQL engine, and is not the backend of the TypeScript v2
SDK fixture. The proxy cells cover one pinned Python SDK HTTP route on one
host. Neither that run nor these extra tests constitute independent human
replication or a distributed exactly-once guarantee.

## Known at design time

1. **Single author, two languages.** The Python and TypeScript adapters establish cross-implementation testing. They are not independent implementers, and their agreement is not external validation.
2. **Fixture tests are machinery tests.** Passing the 12 cases validates the harness. It is not evidence about model or agent behavior.
3. **No exactly-once claim.** Nothing here establishes exactly-once external effects. Any such property depends on the actual backend and the mediation assumptions in force, which this project does not provide.
4. **Scope is local and synthetic.** An SQLite issue-record backend, not payments, not client systems, not an external IdP.
5. **Maintainer intent unknown.** Whether protocol maintainers want this profile is not knowable from inside this repo. Acceptance is outside our control.
6. **Recovery is bounded to the guarded fixture.** The older unmediated crash
   fixture is a control. Guarded cases 03 and 09 test status readback after a
   real stdio lost reply, using one synthetic SQLite backend. They do not prove
   recovery across arbitrary production services.
7. **Synthetic authority.** Principal checks use configured test identities and
   do not validate production authentication middleware.
8. **Historical evidence contains local paths.** Private originals remain
   byte-identical; five files in the history-free public source archive are
   disclosed redacted derivatives. `docs/PUBLIC-VERIFICATION.md` explains the
   public hash boundary.
9. **Metadata stripping may be indistinguishable from absence.** A proxy that removes experimental metadata can leave a receiver unable to tell "unsupported" from "not present." Case 11 tests for this, but the test can only observe what reaches the receiver.

## Structural risks

- **False conformance.** Tests asserting on in-memory objects can pass while the guarantee never reaches the wire. Mitigation: wire-level assertions mandatory.
- **Protocol-machinery creep.** A profile can drift into a competing standard. The deliverable here is evidence and a reference implementation, not a specification.
- **Time decay.** Pinned results remain reproducible evidence about those pins,
  not claims about current SDK releases.

## What would falsify the project's premise

The premise that replay protection was an unspecified SDK duty was falsified by
the official MRTR server requirements. The remaining value is narrower:
reproducible pinned witnesses, cross-language fingerprint vectors, and a tested
example of the server-side mediation the specification requires when
at-most-once behavior matters.
