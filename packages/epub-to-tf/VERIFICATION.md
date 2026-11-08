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
At that stage, SVG and media were still blocked. The supported input remains
unencrypted reflowable EPUB with the explicit limits in the README; DRM and
fixed layout remain blocked.

## Dark QA page and general TF assets

The next increment preserves referenced images, passive SVG, audio, video,
caption tracks, embedded PDF and inline MathML in `tf/assets/`. Document and
note `asset_refs` features retain the TF-relative path, MIME type, kind, source
member and byte offset, Unicode scalar position within that reading scope,
and SHA-256. The earlier document `image_assets` feature remains available.
Active or externally linked SVG and responsive `srcset` remain blocking.

| Command | Result |
| --- | --- |
| `make doctor` / `make fmt` / `make ci` | Passed; root Rust and Swift checks completed. |
| `cargo clippy -p corpora-convert --all-targets --all-features -- -D warnings` | Passed. |
| EPUB package Ruff, format check, mypy, `uv run --group dev pytest -q`, `uv build` | Passed; 31 tests, including SVG/media/note-asset TF and Context-Fabric round trips and dark QA generation. |
| `make -C packages/tei-to-tf check build` | Passed; 138 tests, 11 skipped. |
| Full original Marcion EPUB → `target/qa-marcion-assets/` | Passed; five documents, 252,115 exact characters, nine image assets under `tf/assets/`, unchanged archive hash above. |
| `uv run --project packages/epub-to-tf --group dev python target/qa-marcion-verify.py` | Passed; independently parsed all five XHTML bodies, checked all nine copied image bytes/hashes, and reloaded exact text plus `asset_refs`/`image_assets` with Text-Fabric and Context-Fabric. |
| Static `tf_validate.py target/qa-marcion-assets/tf` | 0 errors, TF064 warning and TF065 info from intentional character slots and no invented separators. |
| `uv run --group dev python tools/qa_browser.py ../../target/qa-marcion-assets ../../target/qa-marcion-browser` | Passed; Aside Browser at `http://127.0.0.1:8769/index.html` showed dark UI, original cover and study-guide chapter, exact text status, and matching source/bundle image previews. Screenshot: `/Users/emmanuel/.aside/u/0/sessions/2026-11-08_yYnt1KNgw9Tr9Vxd/artifacts/marcion-dark-reusable-final.png`. |
| Bundle checksum and cache check | 34 file checksums valid; `tf/assets/` is the only subdirectory under `tf/` after loader caches were removed. |

The browser generator is tracked at `packages/epub-to-tf/tools/qa_browser.py`;
generated pages remain under ignored `target/`. Neither bundle nor source was
committed or pushed by the agent.
