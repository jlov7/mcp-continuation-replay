# Security and integration assumptions

This is a synthetic, local SQLite reference. No real authentication service,
payment backend, external identity provider or general effect broker is
included. The guarantees below apply to the tested server and transaction
boundary.

| Boundary or invariant | Supported behavior and falsifier | Production assumption |
|---|---|---|
| Untrusted tool arguments and input responses | The server validates the body response shape and binds accepted fields into the fingerprint. Changed inputs conflict before effect dispatch (guarded cases 04 and 05). | A caller must enforce authorization for the requested tool and validate all real inputs. |
| Principal and backend identity | The stdio fixture configures a synthetic principal and backend. The additive loopback HTTP adapter maps two fixed public test bearer strings to principals per request; the second cannot read or replay the first principal's result. | Authenticate the real principal and bind it to a trusted backend identifier. The local token map is not production auth. |
| Request state | The SDK signs continuation state and the server checks operation, nonce and deadlines; stripped state is rejected (cases 05, 07, 10, 11). TypeScript v2 state is signed, not encrypted. | Keep signing keys private and rotated appropriately; state contents and digests can reveal equality. |
| Fingerprint key | Both adapters require a 32-byte or longer caller key; cross-language vectors and `test_cli.py` reject invalid inputs. Fixed test keys in transcripts are synthetic fixtures, not deployment credentials. | Provision an actual secret key and control its lifecycle. |
| Deadline and retention | Server clock and bounded token/operation deadlines are explicit. Expiry rejects new effects and retained tombstones prevent stale identity reuse (cases 07 and 10). | A replacement store must retain tombstones for the declared period and use a trustworthy clock. |
| Atomic issue effect | SQLite `BEGIN IMMEDIATE` binds one operation to one issue row. Concurrent first use and replay yield one row (cases 01 and 08); precommit hard exits roll back (`test_fault_lab.py`). | An external backend needs an equivalent atomic identity/effect boundary. Cross-service exactly-once is not established. |
| Lost reply and status | Transport failure remains `unknown`; status-only recovery returns a stored result after exact identity and structured scope checks. Missing ledger and diagnostic title/body queries do not prove non-application. A timezone-aware timestamp is recorded, but an older immutable terminal observation can remain valid. | Status observations must come from the authorized store and bind operation id, principal and backend. A status field is not itself authentication. |
| Partial effects and compensation | Case 12 retains the original issue and a separate failed compensation record. An additive hard exit after the first partial commit leaves `in_progress` and blocks automatic retry. | A real multi-step service must define its own durable partial states, operator path and compensating identities. |

The fixture accepts keys through environment variables and deliberately
allowlists subprocess environment names. Public logs may contain fixed
synthetic keys and request-state tokens; their presence is not evidence of
deployed credentials. If an intermediary strips experimental metadata,
the receiver cannot infer that no effect occurred. Stop and reconcile rather
than dispatching a fresh operation.
