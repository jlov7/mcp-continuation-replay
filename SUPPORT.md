# Tested support boundary

The Python package declares Python `>=3.11`. CI is configured for
CPython 3.11 and 3.13 on Ubuntu with Node 22 for the isolated TypeScript v2
wire fixture. The current local full gate passed on macOS Apple Silicon with
Python 3.11.16 and 3.13.15, using Node 22.23.2. Python 3.12, Python 3.14,
Ubuntu and other operating systems are within the version range where
applicable but have no separate local execution receipt. Check the
[current Actions runs](https://github.com/jlov7/mcp-continuation-replay/actions)
for hosted results on a particular commit; the retained local results do not
establish those results. Report nonsensitive bugs in
the [repository issue tracker](https://github.com/jlov7/mcp-continuation-replay/issues).
Do not put credentials, personal data, or exploit details in an issue. See
[Security](SECURITY.md) for reporting limits.

| Component | Exact pin or scope |
|---|---|
| Python MRTR fixture | `mcp==2.2.0`, `uv.lock` |
| TypeScript v2 guarded fixture | `@modelcontextprotocol/core@2.0.0`, `@modelcontextprotocol/server@2.0.0`, `zod@4.6.5`, `adapters/typescript-v2/package-lock.json` |
| Legacy TypeScript fingerprint adapter | `@modelcontextprotocol/sdk@1.30.0`, TypeScript `5.9.3`, `adapters/typescript/package-lock.json`; no MRTR surface |
| Storage | Local SQLite in the shared Python `IssueStore` |
| Installed wheel | `continuation-replay-fingerprint` JSONL CLI |
| Source-only tools | Guarded stdio server, raw-wire tests, retained verification, public export verifier and demo |

An SDK upgrade must be a separate changeset with lockfile diff, exact protocol
surface check, raw-wire cases, physical readback and a complete outcome table.
The old pinned witness cases remain frozen as historical observations.
