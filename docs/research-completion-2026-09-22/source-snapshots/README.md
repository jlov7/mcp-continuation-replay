# History-free source verification

Seven small snapshots contain only the files named in each passing attempt's
`source_hashes` receipt. Their sidecar manifests bind the source commit, exact
file hashes, archive hash, attempt path, and attempt summary hash. The verifier
checks all of those fields, materializes the source in a temporary directory,
then invokes that attempt's original verifier on its unchanged raw transcripts
and SQLite snapshots. It requires Python and the retained attempt directory,
but no Git repository or installed MCP/Node packages for verification.

Run from this repository or a history-free copy with the same relative files:

```bash
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/python-original-3db5a1d551c0.json \
  --attempt docs/research-completion-2026-09-22/raw/attempt-20260922T182510Z-1790101510523840000
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/python-post-fix-043cd3f1f758.json \
  --attempt docs/research-completion-2026-09-22/raw/attempt-20260922T184821Z-1790102901145313000
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/typescript-v2-before-backend-fix-8c9f30e97a4f.json \
  --attempt docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184411Z-1790102651819382000
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/typescript-v2-post-fix-c6e72f00ffee.json \
  --attempt docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T184836Z-1790102916435739000
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/typescript-v2-strict-response-586e8335c1f8.json \
  --attempt docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T185338Z-1790103218439566000
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/python-final-instrumented-71e08e7eb067.json \
  --attempt docs/research-completion-2026-09-22/raw/attempt-20260922T220129Z-1790114489061895000
python -m scripts.verify_source_snapshot \
  --snapshot-manifest docs/research-completion-2026-09-22/source-snapshots/typescript-v2-final-locked-8361f25baa0b.json \
  --attempt docs/research-completion-2026-09-22/typescript-v2/raw/attempt-20260922T220151Z-1790114511892918000
```

The failed first TypeScript attempt remains in `typescript-v2/raw/` with its
original source hash receipt; it is a retained machinery failure, not a passing
matrix. The source snapshots support rechecking retained observations. They do
not rerun the SDK servers or establish independent storage validation.
