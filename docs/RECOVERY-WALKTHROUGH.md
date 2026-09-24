# One lost reply and one effect

This walkthrough runs frozen guarded case 03 using the real Python SDK stdio
server, `ContinuationConsumer`, and SQLite store. It is a source-archive
workflow requiring the pinned development dependencies; the installed wheel
only provides `continuation-replay-fingerprint`.

After public inventory verification and dependency installation, choose a new
output directory outside the extracted candidate:

```bash
uv sync --locked --extra dev
uv run python -m scripts.demo_lost_reply --output-dir /tmp/mcp-case-03
```

The script executes the existing case 03 test and reads its raw wire transcripts
and SQLite file. The result includes:

```json
{
  "input_required": true,
  "operation_id": "case-03",
  "transport_after_commit": "unknown; no reply",
  "status": {"operationId": "case-03", "principal": "alice", "backend": "sqlite:guarded-matrix", "state": "applied", "authoritative": true, "freshWriteAuthorized": false, "matchingIds": [1]},
  "replay": {"operationId": "case-03", "effectId": 1, "replayed": true, "state": "applied"},
  "physical_issue_rows": 1,
  "physical_operation_rows": 1
}
```

The first call yields `input_required` and a signed request-state token. The
continuation commits the issue and operation ledger in one SQLite transaction;
the fixture then exits before sending a reply. The consumer calls that
transport outcome `unknown`. After restart, `get_operation_status` returns an
identity-bound authoritative observation. The original demo then makes an
exact replay and receives the stored result with one physical issue row.
The additive `tests/test_next_recovery.py` stops after status: it validates
the status `storedResult`, gives that value to `ContinuationConsumer`, and
checks the restart transcript contains only `get_operation_status`. No
continuation is redispatched. Both routes prohibit a fresh write.
The raw transcripts and database are kept under the chosen output directory.

`tests/test_unsafe_control.py` is the deliberately unsafe changed-identity
control: a fresh identifier creates a second effect. It is not a recovery
instruction. Case 04 shows changed inputs under the *same* identifier
conflicting before dispatch. Case 09 shows read-only recovery without a
redispatch. Case 12 shows a committed partial effect and failed compensation.
