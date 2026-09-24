# Related work and scope

Selected primary-source reading checked 2026-09-24, not a systematic literature
review. See [current findings](CURRENT-FINDINGS.md) for this project's interpretation.

| Work | Relevant scope | Boundary of this artifact |
|---|---|---|
| [MCP 2026-07-28 MRTR pattern](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr) | Defines multi-round requests and explicitly says request-state binding does not guarantee single use; servers needing at-most-once behavior must enforce it. | The reference ledger demonstrates one narrow server-side implementation under SQLite assumptions. |
| [AAI Foundation `requestState` design note](https://aaif.io/blog/designing-requeststate-for-multi-round-trip-requests) (2026-08-12) | Separates integrity binding from replay policy and describes nonce/redemption with durable state. | Explains why the pinned unmediated probe needs an application mechanism for at-most-once effects. |
| [MCP PR #3182, Request Idempotency](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182) | Proposed a separate idempotency mechanism and explicitly excluded MRTR continuation equivalence. Closed 2026-08-23. | The witness vectors cover that excluded interaction but do not make it an SDK defect. |
| [MCP PR #3312, structured tool failure](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3312) | Drafts failure classification and retry guidance. Open at the check date. | A reported failure still does not prove backend state. |
| [`RequestStateBoundary` in pinned Python SDK 2.2.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/server/request_state.py) | Protects integrity, freshness, audience, principal, and request binding. | It does not claim durable redemption; the server supplies that when needed. |
| [`idempotentHint`](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) | Static tool-level statement about repeated equal arguments. | It is not durable proof that a particular continuation effect occurred. |

## Non-claims

- No novelty claim for idempotency, redemption ledgers, at-most-once delivery,
  or unknown-outcome reconciliation.
- No normative defect claim against the pinned Python SDK.
- No statement that the pinned TypeScript 1.30 surface describes newer
  prereleases.
- No independent replication or external validation.
