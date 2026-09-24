# Contributing

This is a bounded experimental repository. Start with [current findings](research/CURRENT-FINDINGS.md), [architecture](docs/ARCHITECTURE.md), [development checks](docs/DEVELOPMENT.md), and [AI assistance disclosure](docs/AI-ASSISTANCE.md). The [repository guide](docs/REPOSITORY-GUIDE.md) distinguishes maintained docs from frozen evidence.

## What a change needs

- A concrete scenario or bug reproduction and the smallest change that addresses it.
- Raw-wire assertions for wire behavior, plus independent physical SQLite readback for effect claims. An in-memory object assertion cannot establish what reached the consumer.
- Preservation of the ten exact pinned unguarded witness tests. The full gate verifies their node IDs, mechanism labels, and execution. If a pinned observation changes, investigate the source and wire evidence; do not relabel an expected control as an SDK defect.
- Exact dependency pins and a recorded runtime when changing SDK compatibility claims. `mcp==2.2.0`, legacy `@modelcontextprotocol/sdk@1.30.0`, and the separate TypeScript v2 pins measure different surfaces.
- A `STATUS.md` entry when behavior or protocol interpretation changes, with a link to retained evidence.
- A factual disclosure of AI assistance used for the contribution. AI review is not independent replication.

Run the commands in [development checks](docs/DEVELOPMENT.md) for code or runtime changes. Focused selections omit `--verify-pinned-findings`; report them as focused checks. Keep generated test output outside the checkout where practical.

For a protocol claim or proposed upstream contribution, verify the current [MCP specification](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr) and explain how your evidence relates to its server responsibilities. Follow the destination project's contribution and AI-disclosure policies. This repository does not submit a protocol change.
