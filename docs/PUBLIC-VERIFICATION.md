# Public export verification

The pristine verification commands below apply to the generated release export
ZIP. A Git checkout may omit a prior `EXPORT-MANIFEST.json`. Clone the Git repository or use a checkout
with its Git history, then build an export with
`python3 -B -m scripts.build_public_export --source-kind already-public DESTINATION`
and verify its newly extracted ZIP. The automatic source ZIP alone lacks the Git
commit context required by the builder.

The source ZIP is a history-free derivative of one committed tree. Its
`EXPORT-MANIFEST.json` lists every regular file **except the manifest itself**,
including the shipped verifier. A release receipt beside the ZIP must state the
ZIP SHA-256 and source commit. The ZIP hash binds the manifest and verifier;
there is no circular self-hash claim. Without a separately obtained trusted
receipt, the commands below check internal consistency, not publisher identity.

From a newly extracted candidate, before installing or running code in it:

```bash
python3 -B -m scripts.verify_public_export --inventory-only
python3 -B -m scripts.verify_public_export
```

The first command rejects missing, extra, linked, non-regular, unsafe or
case-colliding paths, invalid modes, changed SHA-256 values, malformed status
and transform metadata. The second replays the final Python and TypeScript v2
12-cell retained matrices through their exact source-snapshot verifiers. Those
replays read retained wire transcripts and physical SQLite snapshots without
Git history or SDK packages. They do not rerun the live SDK servers. The direct
historical verifiers properly reject changed current source hashes; current
behavior is checked by the live tests.

The five disclosed derivatives replace local path or pytest username text in
historical logs. Their `exported_sha256` values are checked against the public
bytes. In a v2 private-origin export, `original_sha256` and `git_blob_sha1`
describe private originals; a
public reader cannot rehash originals that were deliberately omitted. The
historical original hashes describe the private originals, not the redacted
public logs. Do not interpret those checks as passing on the exported derivative.

For a release ZIP, compare its SHA-256 with the separately distributed receipt
*before* extraction. The release builder is
`python3 -B -m scripts.build_public_export DESTINATION`; it requires a clean committed tree,
rejects tracked links and credential/runtime paths, and creates a deterministic
ZIP and extracted tree. It never includes Git history, untracked files,
dependencies or local caches. The final release receipt is produced only after
the reviewed candidate is built and read back.

The installed wheel contains the fingerprint command. The guarded stdio
server, raw-wire tests, demo, retained evidence and export verifier are source
checkout tools. Running tests, an installer or the demo inside the extracted
tree can create files that intentionally fail the pristine inventory check;
put outputs in a separate directory and verify the pristine extraction first.

A public Git repository seeded from the sanitized source has a different input
contract: its five historical files are already redacted. Use
`python3 -B -m scripts.build_public_export --source-kind already-public DESTINATION`
there. This creates a v3 manifest. Each retained derivative records the
current public Git blob and SHA-256 as its source bytes, plus separately named
private-origin hashes that remain unverified provenance assertions. The five
public byte hashes are fixed; changing one fails the build. A tracked prior
`EXPORT-MANIFEST.json`, if tracked, is replaced in the new archive and disclosed as one
omission. Its private-origin commit is carried forward across later public Git
revisions when present. If the prior manifest is absent, the new manifest states
`origin_private_commit: null`; the external original release receipt remains
the source of that provenance. The new manifest exists only in the generated
archive, so no recursive commit-hash assertion is made.

The private source route remains `--source-kind private-origin` (the default).
CI chooses between the two explicit routes by comparing all five files with
the fixed approved public hashes. A mixed match fails. When seeding a public
Git repository from the extracted archive, stage every candidate file,
including files matched by `.gitignore`; ordinary `git add -A` can omit retained
evidence logs. The archive's external SHA-256 receipt remains the release
anchor for either route.
