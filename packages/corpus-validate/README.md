# Corpus archive validation

`corpora-corpus-validate` accepts a bounded corpus archive and reports whether
Text-Fabric and Context-Fabric can load its data. Its CLI is a JSON boundary for
`corpora-api`:

```sh
uv run corpora-validate /absolute/path/to/mini.corpus --name mini.corpus
```

The caller stages an uploaded archive locally. The reported `path` is the public
filename, never the staging path. `.zip` holds one Text-Fabric dataset; `.corpus`
also requires the shipped `.cfm` cache to load and match a fresh compilation.
`.cusx` and `.ctei` use their legacy package profiles, with member hashes,
source projections, and TEI schemas checked as applicable. The TEI schema assets
come from the MIT-licensed `exegia/corpora-py` repository; upstream provenance
is retained in `src/corpus_validate/profile/provenance.json`.
The validator rejects unsafe ZIP members, archives over 3 MB, more than 3,000
members, and over 64 MB unpacked. Invalid supported archives return a JSON
verdict with `valid: false`; unsupported formats and size violations produce a
JSON error with process exit status 2.

Validation checks loadability and sampled cache consistency. It does not prove
source fidelity or semantic correctness. The existing API Text-Fabric checker
is a separate static WARP preflight.

Run `uv sync --locked && uv run pytest` in this directory. Tests create a small
corpus and load it through both real runtimes, including the `.cfm` mmap cache.
