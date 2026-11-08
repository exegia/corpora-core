# First EPUB conversion verification

2026-11-08, branch `feat/convert-epub-to-tf`, local uncommitted work.

| Command | Result |
| --- | --- |
| `make doctor` | Required root tools available. |
| `make fmt` | Passed. |
| `make ci` | Passed after the converter Clippy fixes; Rust, Swift, agent checks, tests and builds. |
| `cargo build -p corpora-convert --bin corpora-epub-check` | Passed. |
| `uv run --group dev ruff check .` (package) | Passed. |
| `uv run --group dev ruff format --check .` (package) | Passed. |
| `uv run --group dev mypy src` (package) | Passed. |
| `uv run --group dev pytest -q` (package) | 15 passed, including actual Text-Fabric and Context-Fabric loads. |
| `uv build` (package) | Wheel and source distribution built. |
| `make -C packages/tei-to-tf check build` | 138 passed, 11 skipped; lint, type and build passed. |
| `git diff --check` | Passed. |

Static `tf_validate.py` on the generated 11-slot fixture returned 0 errors,
TF064 warning, TF065 info. Those findings are caused by intentional character
slots: slots 7 and 9 contain literal spaces, and `{text}` deliberately adds no
separator. Exact `T.text(document)` was checked against the independently
specified `Áβcafé & 東京` using both real loaders.

`doc_schema.py` followed by `tf_reconcile.py` reported RC001/RC002 against
that same fixture. Its EPUB reference extractor treats the adjacent inline
`Á<em>β</em>` as separate words (`Á β`), while the XHTML source has no space
and the converter correctly preserves `Áβ`. This reconciliation is unsuitable
as an acceptance oracle for adjacent inline characters; the independent
source-text assertion and loader round trips are the acceptance evidence.

No hosted service or remote acquisition was used. No commit or push was made in this initial run.

## Separate note slots and references

On `feat/convert-epub-to-tf`, the follow-up note implementation passed:

| Command | Result |
| --- | --- |
| `make doctor` / `make fmt` / `make ci` | Passed. |
| `cargo clippy -p corpora-convert --all-targets --all-features -- -D warnings` | Passed. |
| `cargo build -p corpora-convert --bin corpora-epub-check` | Passed. |
| EPUB package Ruff, format check, mypy, `uv build` | Passed. |
| EPUB package `uv run --group dev pytest -q` | 24 passed; note text and links loaded by Text-Fabric and Context-Fabric. |
| `make -C packages/tei-to-tf check build` | 138 passed, 11 skipped; lint, types and build passed. |
| `git diff --check` | Passed. |

The generated 22-slot note fixture passed `tf_validate.py` with zero errors.
TF064 (whitespace character slots) and TF065 (`{text}` intentionally adds no
separator) remain expected static notices. Independent tests assert exact main
text `Alpha1 omega!`, exact note text `Note beta`, the marker-to-note edge,
cross-member links and deterministic `.tf` bytes. No database tables were
created. This follow-up was not committed or pushed by the agent.

## Full Marcion EPUB with images

The original local Marcion EPUB (archive SHA-256
`8215230be4c7ec3c950868fdadad0c248879473ffb5a580ef34edff32b22bec1`)
now validates without source edits. Its five linear spine documents and nine
JPEG references export to `target/qa-marcion-full/`. Each image keeps its source
member, raw member-byte location, Unicode scalar text position, alt text,
media type and exact-byte hash; copied assets total 814,665 bytes. The EPUB
itself remains preserved under `sources/original.epub`.

| Command | Result |
| --- | --- |
| `cargo build -p corpora-convert --bin corpora-epub-check` and `target/debug/corpora-epub-check ORIGINAL.epub` | Passed, zero blocking findings. |
| `uv run --project packages/epub-to-tf epub-to-tf ORIGINAL.epub target/qa-marcion-full --checker target/debug/corpora-epub-check` | Passed; OPF UUID retained. |
| `uv run --project packages/epub-to-tf --group dev python target/qa-marcion-verify.py` | Passed: independently parsed all five original XHTML bodies; exact 4, 839, 99,441, 137,868 and 13,963 character matches; all nine image bytes/hashes; real Text-Fabric and Context-Fabric document and image feature loads. |
| `python3 /Users/emmanuel/.agents/skills/text-fabric-validator/scripts/tf_validate.py target/qa-marcion-full/tf --report target/qa-marcion-static.md --json target/qa-marcion-static.json` | 0 errors, TF064 warning and TF065 info. Literal whitespace character slots and intentional no-separator format explain both findings; both loaders returned exact full source text. |
| Aside Browser, `http://127.0.0.1:8769/index.html` | Inspected cover and final study-guide chapter. Original XHTML rendered, text-match status shown, and nine image references/asset previews available across the five-document selector. Screenshot: `/Users/emmanuel/.aside/u/0/sessions/2026-11-08_yYnt1KNgw9Tr9Vxd/artifacts/marcion-full.png`. |
| `make fmt` then `make ci` | Passed after fixing three Clippy findings. |
| EPUB package Ruff check, format check, mypy, pytest, `uv build` | Passed; 27 tests after the final SVG rejection test. |
| `make -C packages/tei-to-tf check build` | Passed; 138 tests, 11 skipped. |

The QA script and browser files live in ignored `target/`, not in the exported
bundle or tracked source. Loading a bundle with Context-Fabric can create
runtime `.cfm` caches afterward; the exporter removes caches before publication.
The accepted input remains unencrypted reflowable EPUB with the explicit
limits in the README. DRM, fixed layout, SVG and scripted/rich media are still
blocked rather than represented as a successful but incomplete conversion.
