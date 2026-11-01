# Related work and scope

Selected primary-source reading checked through 2026-10-31, not a systematic literature
review. Other authors' experiments were not reproduced. See
[current findings](CURRENT-FINDINGS.md) for this project's interpretation.

| Work | Relevant scope | Boundary of this artifact |
|---|---|---|
| [MCP 2026-07-28 MRTR pattern](https://modelcontextprotocol.io/specification/2026-07-28/basic/patterns/mrtr) | Defines multi-round requests and explicitly says request-state binding does not guarantee single use; servers needing at-most-once behavior must enforce it. | The reference ledger demonstrates one narrow server-side implementation under SQLite assumptions. |
| [MCP Tasks extension (2026-07-28)](https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks) | A server assigns a durable task ID before returning `CreateTaskResult`; the specification says MRTR should resolve before task creation. | Tasks support later lookup when the client receives the ID. If that response is lost, this fixture's client-chosen operation ID and read-only status route address a different recovery gap. The extension is not a general exactly-once guarantee. |
| [AAI Foundation `requestState` design note](https://aaif.io/blog/designing-requeststate-for-multi-round-trip-requests) (2026-08-12) | Separates integrity binding from replay policy and describes nonce/redemption with durable state. | Explains why the pinned unmediated probe needs an application mechanism for at-most-once effects. |
| [MCP PR #3182, Request Idempotency](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182) and its [1 August continuation discussion](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3182#issuecomment-5151553269) | The proposal excluded MRTR from its final scope. Its discussion already articulated same-continuation replay and changed-state/input-response conflicts. | The vectors make this interaction executable under pinned SDKs. They do not establish a new replay policy or SDK defect. |
| [MCP PR #3312, structured tool failure](https://github.com/modelcontextprotocol/modelcontextprotocol/pull/3312) | Drafts failure classification and retry guidance. Open at the check date. | A reported failure still does not prove backend state. |
| [`RequestStateBoundary` in pinned Python SDK 2.2.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/server/request_state.py) | Protects integrity, freshness, audience, principal, and request binding. | It does not claim durable redemption; the server supplies that when needed. |
| [`idempotentHint`](https://blog.modelcontextprotocol.io/posts/2026-03-16-tool-annotations/) | Static tool-level statement about repeated equal arguments. | It is not durable proof that a particular continuation effect occurred. |
| Birrell and Nelson, [Implementing Remote Procedure Calls](https://www.cl.cam.ac.uk/teaching/0708/DigiCommI/birrell1984rpc.pdf), 1984, §§3.1–3.2 | Call identities and callee records suppress duplicates; exceptions can leave execution uncertain. | Operation identity and uncertain outcomes are established RPC concerns. |
| Lee et al., [Implementing Linearizability at Large Scale and Low Latency](https://web.stanford.edu/~ouster/cgi-bin/papers/rifl.pdf), SOSP 2015, §§3–4 | RIFL records completion results atomically with effects and handles retry rendezvous, retention and concurrency under its storage assumptions. | The SQLite effect-and-ledger transaction applies established recovery principles. Neither system establishes arbitrary external-effect atomicity. |
| [Making retries safe with idempotent APIs](https://aws.amazon.com/builders-library/making-retries-safe-with-idempotent-APIs/), Amazon Builders' Library | Caller-scoped request identities, stored replay responses and same-ID/different-parameter rejection. | Continuation state and accepted input responses specialise the effective request being compared. |
| [Idempotency-Key HTTP Header Field, draft-08](https://datatracker.ietf.org/doc/html/draft-ietf-httpapi-idempotency-key-header-08), 22 October 2026, §§2.2–2.7 | Describes payload fingerprints, expiration policy and concurrent request conflicts. This is a work-in-progress Internet-Draft, not an RFC. | The reference fingerprint and retention policy are application choices, not a new general mechanism or MCP requirement. |
| Mansoor et al., [Verified Tool Calls Improve LLM Agent Reliability Under Non-Atomic Failures](https://arxiv.org/html/2608.02645v1), §§4.4–4.7 | Read-only three-valued verification, idempotency keys and verification before retry in simulated workflows. | The reference status route is related implementation evidence. This artifact does not measure model improvement. |
| Jiapeng Li, [Where Does Exactly-Once Live?](https://arxiv.org/html/2609.29095v1), §§2–5 | Discusses effect ledgers, late commits, partial effects and limits of negative readback. | These broader results are not reproduced here. Local SQLite recovery does not establish a general exactly-once guarantee. |
| [Lost-response fixture PR #2](https://github.com/arjun2075/mcp-b1-lost-response-repro/pull/2) and [Shipjack retry vectors at f2618f3](https://github.com/Srivatsa03/shipjack/blob/f2618f3280d2530de13bfed0544fed06507c29c7/docs/MCP_RETRY_VECTORS.md) | Adjacent executable MCP retry work reports changed-argument conflicts and uncertain-outcome cases. Shipjack also reports process restart and concurrency. | These are contributor-reported checks, not this project's replication. Restart and concurrency tests alone do not distinguish this artifact as new research. |

## Non-claims

- No novelty claim for idempotency, redemption ledgers, at-most-once delivery,
  or unknown-outcome reconciliation.
- No normative defect claim against the pinned Python SDK.
- No statement that the pinned TypeScript 1.30 surface describes newer
  prereleases.
- No independent replication or external validation.
