# Local transport and native-store study protocol

Version 1, frozen before E/F/G outcome runs. This is local engineering evidence
designed after the historical twelve-case matrices were visible. It is neither
a blinded study nor outside replication. Retain failures and any unsupported
cells; changes to a cell require a new protocol version and a separate result.

Amendment 1.1, before the next E/G run: the first permitted HTTP attempt
returned 400 before dispatch because its raw client omitted the required
modern HTTP `Mcp-Method` and `Mcp-Name` routing headers. The corrected client
and intermediary forward both headers. The first attempt and failed retry are
retained separately; the three transport fault schedules and expected effects
are unchanged.

Amendment 1.2, before repeating F: the two concurrent native-store processes
now use a test barrier. The first holds SQLite `BEGIN IMMEDIATE`, signals it
has entered the transaction, and waits for the second to signal its attempt.
The first releases after a bounded 200 ms hold while the second attempts its
own `BEGIN IMMEDIATE`. The earlier two-process start-time comparison did not
prove competing transaction attempts. The expected one-effect/one-ledger
outcome and independent physical readback remain unchanged.

Amendment 1.3, before another F run: the first coordinated attempt timed out.
The second process tried to initialize the SQLite schema while the first held
the writer transaction, so it could not reach its attempt signal. The amended
schedule opens both stores first. The second emits a ready marker and waits;
the first enters and holds `BEGIN IMMEDIATE`, then the test releases the second
to attempt its transaction. The timeout and failed attempt remain in the
coordinator evidence. Expected physical outcomes remain unchanged.

## E: authenticated test requests

Use the released Python `mcp==2.2.0` modern Streamable HTTP handler at
`127.0.0.1` with an outer loopback test-token verifier. Fixed in-memory test
tokens map to `alice` and `bob`; missing, malformed and wrong tokens are denied
before MCP dispatch. Principal is selected per HTTP request by the verifier,
not by tool arguments. Alice's status-only read must return her applied result;
Bob's request for the same operation ID must not reveal it or replay its effect.
The same state token presented by Bob must be rejected. The verifier, its token
map, local host and process are trusted. This does not test OAuth, TLS, real
accounts, revocation or production authentication.

## F: native TypeScript store

Use Node's `node:sqlite` and a separate TypeScript transition implementation.
The TypeScript engine must not call Python. Fixed cells: (1) commit then lose
reply, reopen database, recover the stored value by status with one effect;
(2) changed fingerprint under one operation ID conflicts before effect;
(3) two process-level concurrent first uses leave one effect and one ledger
row; (4) a retained operation at or past replay expiry rejects reuse; (5)
status on an absent row is unknown and cannot authorize a write. Read SQLite
tables with a separate read-only Python query after the Node processes exit.
An unsafe changed-identity control must produce two rows, proving the effect
detector sees duplicates. Runtime and file hashes go in the result. Shared
test authorship, a common SQL engine, and local hardware limit corroboration.

## G: intermediary and transport

Capability precheck: the installed `mcp==2.2.0` server has
`MCPServer.streamable_http_app` and `run_streamable_http_async`; its modern
2026-07-28 path accepts one HTTP POST exchange and MRTR result types. Record
the exact installed version at run time. Use a real `127.0.0.1` HTTP proxy
between a raw client and the SDK HTTP server. Preserve request and response
bytes in separate client-proxy and proxy-server logs. Three cells:

1. Drop the committed continuation's upstream response: client outcome unknown;
   status-only recovery returns one stored result and physical effect count one.
2. Delay the committed continuation's response beyond a bounded client read
   deadline: client outcome unknown; status-only recovery returns one result,
   physical effect count one. The late response is retained as a proxy event.
3. Strip `requestState` from a continuation on the proxy-server side: server
   rejects before any new effect; client-proxy and proxy-server bytes differ.

If a released SDK route cannot represent a cell, record `UNSUPPORTED` with
the concrete API limit and no synthetic pass. No hosted proxy or production
network claim follows from local loopback behavior.
