# Corpus archive validation and read views

`corpora-corpus-validate` accepts a bounded corpus archive and reports whether
Text-Fabric and Context-Fabric can load its data. Its CLI is a JSON boundary for
`corpora-api`:

```sh
uv run corpora-validate /absolute/path/to/mini.corpus --name mini.corpus
```

The caller stages an uploaded archive locally. The reported `path` is the public
filename, never the staging path. `.zip` holds one Text-Fabric dataset; `.corpus`
also requires the shipped Context-Fabric cache to load and match a fresh compilation.
`.cusx` and `.ctei` use their legacy package profiles, with member hashes,
source projections, and TEI schemas checked as applicable. The TEI schema assets
come from the MIT-licensed `exegia/corpora-py` repository; upstream provenance
is retained in `src/corpus_validate/profile/provenance.json`.
The validator rejects unsafe ZIP members, archives over 3 MB, more than 3,000
members, and over 64 MB unpacked. Invalid supported archives return a JSON
verdict with `valid: false`; unsupported formats and size violations produce a
JSON error with process exit status 2.

`corpus_validate.read_archive(data, view, **params)` reads `manifest`, `index`,
`sections`, `content`, one `node`, or `versions` from an archive. The versions
view preserves `history.yml` entries when present, otherwise it returns the
legacy packaged-manifest entry. It does not inspect an embedded Git repository.
Text-Fabric views open a
single shipped Context-Fabric `.cfr` cache directly when present. Each call
extracts into a private temporary directory and keeps no cross-request cache;
the caller is responsible for authenticating the owner and selecting archive
bytes.

`corpus_validate.reference.reference_archive` creates and resolves versioned
Text-Fabric references, ranges, and compact tokens against the supplied archive.
It uses the archive's manifest version and Context-Fabric loader; callers select
and authorize the archive before calling it. The grammar and compact-token
implementation are adapted from MIT-licensed `exegia/corpora-py` revision
`663eec793b384bca22afbb065678573e21ed5b97`, including its reference fixtures.

Validation checks loadability and sampled cache consistency. It does not prove
source fidelity or semantic correctness. The existing API Text-Fabric checker
is a separate static WARP preflight.

`corpus_validate.ai_archive.validate_archive_scope` checks a version-bound
selection from one caller-authorized archive snapshot. It rejects stale text
hashes and returns node-located findings. Its scoped selection and validation
rules are adapted from MIT-licensed `exegia/corpora-py` revision
`663eec793b384bca22afbb065678573e21ed5b97`.

Run `uv sync --locked && uv run pytest` in this directory. Tests create a small
corpus and load it through both real runtimes, including the `.cfr` mmap cache.

`corpus_validate.version_edit.prepare_edit` prepares a manifest patch or node
annotation from already-authorized `.corpus` bytes. It checks the expected
version and full-byte digest, preserves unrelated ZIP members, updates the
manifest, versioned TOC (when present), and history, and revalidates the
result. Archives without history gain a clearly marked packaged-snapshot
baseline with no invented author or timestamp. Existing malformed history or
annotations are rejected. Node annotations remain sidecar data; converted
Text-Fabric types and source text are not rewritten.

`prepare_restore` prepares a new revision from a previously selected snapshot;
it carries forward the current timeline and records the selected version and
revision. Both operations return `PreparedEdit` with archive bytes, digest,
version, and result metadata. They do not authenticate users, choose storage
paths, or publish. The caller must bind each snapshot revision to the verified
owner **and document**, obtain the bytes and digest from that registry (never
from an archive's legacy `snapshot_key`), and atomically compare and swap the
current head while recording the new revision. `name` must be a flat `.corpus`
filename. The inputs remain immutable and no storage mutation occurs here.
