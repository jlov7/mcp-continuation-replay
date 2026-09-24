# Repository guide

Use [README](../README.md) to start, [architecture](ARCHITECTURE.md) for the current component map, [development](DEVELOPMENT.md) for live gates, and [public verification](PUBLIC-VERIFICATION.md) for source archive custody. These are the maintained routes. The paths below serve different purposes; frozen records remain intact even where their early interpretation was superseded.

| Path | Purpose |
|---|---|
| `src/continuation_replay/` | Installable Python fingerprint contract and JSONL command. |
| `adapters/typescript/` | Legacy pinned TypeScript fingerprint parity adapter; no MRTR server. |
| `adapters/typescript-v2/` | Locked current-v2 SDK dependencies for guarded wire integration. |
| `reference/` | Source-only synthetic SQLite backend, guarded Python server, TypeScript bridge/server, readback and consumer. |
| `scripts/` | Demo, live/retained matrix runners, fault lab, source snapshot and public export tools. |
| `tests/`, `typescript_v2_tests/` | Pinned unguarded witnesses, guarded wire cases, regression/fault tests and shared vectors. |
| `research/CURRENT-FINDINGS.md` | Current interpretation of the spec, pinned observations, and claim limits. |
| `research/LIMITATIONS.md`, `research/RELATED_WORK.md`, `SECURITY-AND-ASSUMPTIONS.md` | Scope, predecessor context and trust assumptions. |
| `docs/research-completion-2026-09-22/` | Frozen protocols, exact source snapshots, retained Python/TypeScript v2 attempts, and verification logs. |
| `docs/public-readiness-2026-09-23/` | Retained fault-lab evidence added after the frozen study. |
| `artifacts/evidence/` | Earlier retained wire evidence; do not rewrite it to match current prose. |
| `research/PROTOCOL.md` | Original experiment protocol. |
| `.github/`, `pyproject.toml`, `uv.lock`, adapter lockfiles | CI and pinned build/test configuration. |
| `STATUS.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `SUPPORT.md`, `SECURITY.md`, `CITATION.cff`, `LICENSE` | Stewardship, release history, contribution and citation routes. |

The installed wheel includes only `src/continuation_replay/` and the fingerprint command. The guarded servers, recovery demo, retained matrices, and export tools require the source tree. Python and TypeScript v2 guarded cases use the same Python SQLite backend; their separate pass counts do not show independent persistence.
