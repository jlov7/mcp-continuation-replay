# TypeScript v2 machinery attempt log

The first result-bearing attempt was
`raw/attempt-20260922T184055Z-1790102455601597000` at source commit
`82cb3ba8d89cdf11f7e43794877b6efc2d822511`. It executed all twelve
requested cells. Eleven passed; case 08 was a machinery error. Both worker
processes reached the continuation barrier. Each then opened a new Python
bridge process against a database that had not yet been initialized, because
minting state did not touch SQLite. Both bridge processes attempted to insert
the singleton `store_metadata.backend_id` key. One received
`sqlite3.IntegrityError: UNIQUE constraint failed: store_metadata.key`.
This is a concurrent schema-bootstrap race, not evidence about whether a
completed operation replays safely. The failed attempt and its raw transcripts
remain retained.

An initial correction added a read-only `status` lookup at TypeScript server
startup. It initialized the empty schema before the two workers were released,
without creating an operation or issue row. Twenty focused case-08 repetitions
passed, then the full second attempt
`raw/attempt-20260922T184411Z-1790102651819382000` passed 12/12 at source
commit `8c9f30e97a4fe8a98533d1debc2d4c746efab18e`. That workaround did not
make simultaneous first-use construction safe for other callers.

The shared Python `IssueStore` was subsequently fixed at source commit
`043cd3f1f7586a443be443a6fe89243c90426251`: metadata binding and schema
creation now use one immediate SQLite transaction. Concurrent fresh-database
constructors with the same backend ID succeed; conflicting IDs leave one
accepted and one rejected binding. The post-fix TypeScript attempt
`raw/attempt-20260922T184836Z-1790102916435739000` passed 12/12 at source
commit `c6e72f00ffee3e4740740000fd83097d33a058a8`. The original failed
attempt and both passing attempts remain retained as separate evidence.

A later strict-response validation fix rejects extra accepted response fields
before fingerprinting or applying an effect. Four focused wire variants and a
boolean-version bridge falsifier passed. The final
`raw/attempt-20260922T185338Z-1790103218439566000` at source commit
`586e8335c1f8a5422c663de3b1476dd1f4241397` again passed 12/12. Earlier
attempts remain unchanged and can be checked against their own source snapshots.

The in-repository isolated v2 runtime lock and subprocess coverage wiring were
added after that attempt. The final
`raw/attempt-20260922T220151Z-1790114511892918000` passed 12/12 at source
commit `8361f25baa0b1c0a5d138f2905afdc495f8994ed`; the matching Python
attempt passed 12/12 at source commit
`71e08e7eb0673c3902205456d815c29a749843ec`. Both have exact source
snapshots and preserve all earlier evidence.
