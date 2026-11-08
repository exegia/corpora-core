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

## The 2001 Translation source trial

The local EPUB at `~/Library/Mobile Documents/com~apple~CloudDocs/Library/The-2001-Translation.epub`
was first hydrated from iCloud through Finder. Its original archive SHA-256 is
`7908e6cf2fbf4ec572109e1fe849843128a37b20e926cc3dba602e419a0f5067`.
The OPF has 73 spine references. Validation read 179 archive members and
projected 63 XHTML documents, 3,718,539 characters and 93 image references,
but blocked full export with 20 findings:

- `EPUB_XML` × 10: malformed XHTML, including mismatched closing tags and
  `ezra-alpha.xhtml`'s invalid attribute names.
- `EPUB_NOTE_ID` × 9: duplicate verse fragment IDs in Daniel, 1 Enoch and
  1 Maccabees. These are source identity ambiguities and remain blocking.
- `EPUB_LIMIT` × 1: the partial reading projection already exceeds the
  one-million-character safety bound.

`target/debug/corpora-epub-check SOURCE > target/qa-2001-check.json` exited 1.
The `epub-to-tf SOURCE target/qa-2001-bundle --checker
target/debug/corpora-epub-check` attempt exited 2, and no output directory
was created. There was therefore no TF or Context-Fabric bundle to load.
The dark source-review page at `http://127.0.0.1:8770/index.html` lists each
finding and opens its original XHTML member; the Aside screenshot is
`/Users/emmanuel/.aside/u/0/sessions/2026-11-08_lkr6GcukLwQg608g/artifacts/2001-translation-blockers.png`.
The browser itself displayed an XML parse error for `numbers.xhtml`.

This trial exposed a diagnostic coordinate bug: roxmltree reports columns in
Unicode scalars, while the validator had added them as byte counts. The narrow
fix now maps scalar columns back to UTF-8 byte offsets. A Unicode malformed-XML
fixture passed, and all ten XML findings now have member-source locations.
The original archive was not modified; no source repair was applied.

After the coordinate fix, `make fmt` and `make ci` passed. EPUB Ruff, format,
mypy and `uv build` passed; `uv run --group dev pytest -q` reported 32 passed.
`make -C packages/tei-to-tf check build` passed with 138 tests and 11 skips.

## The 2001 Translation repaired full conversion

An explicit repair phase now converts this same original archive without
altering it. The Rust checker first reports ten malformed XHTML members and
nine duplicate IDs. HTML recovery is accepted only when an independent
lexical parse finds identical decoded body text, no lost explicit start tags,
and no lost attributes. XML recovery was rejected during the probe because it
lost most of `numbers.xhtml`. The parser's chosen nesting and any invalid
attribute mappings are in `sources/repair-ledger.json`. Sixteen later duplicate
IDs across four members received deterministic suffixes after a scan confirmed
no inbound XHTML references to those ambiguous fragments. Seven of those
duplicates became visible only after malformed chapters were recovered.

The repaired archive SHA-256 is
`56ecf885717f09c833d03e64e25642770fae194f9f1a3976ee9957b48498ef6d`.
The unchanged original remains at `target/qa-2001-bundle/sources/original.epub`;
the separately validated candidate is at `sources/repaired.epub` in that bundle.
Final Rust validation reported zero findings. The bundle contains 73 spine
documents, 5,229,951 character slots, 5,394,552 TF nodes, 118 referenced
assets, 10 XHTML recovery records and four ID repair records.

| Command | Result |
| --- | --- |
| `cargo build -p corpora-convert --bin corpora-epub-check` | Passed. |
| `uv lock --project packages/epub-to-tf` | Added pinned lxml 6.1.3. |
| `uv run --project packages/epub-to-tf epub-to-tf SOURCE target/qa-2001-bundle --checker target/debug/corpora-epub-check --repair --max-slots 8000000` | Passed; final checker report has zero findings and the exporter loaded the generated TF. `SOURCE` is the iCloud path above. |
| `uv run --project packages/epub-to-tf --group dev python target/qa-2001-verify.py` | Passed; independent lexical body parse of all 73 original XHTML members matched each generated document and Context-Fabric `T.text()`, all 263 bundle checksums matched. |
| `python3 /Users/emmanuel/.codex/skills/text-fabric-validator/scripts/tf_validate.py target/qa-2001-bundle/tf --json target/qa-2001-tf-validation.json --report target/qa-2001-tf-validation.md --quiet` | Passed with zero errors; TF064 warns about sampled whitespace character slots and TF065 records the deliberate absence of inserted separators. |
| `uv run --group dev python tools/qa_browser.py ../../target/qa-2001-bundle ../../target/qa-2001-browser` | Passed; Aside Browser at `http://127.0.0.1:8771/index.html` showed 73 chapters, an exact match for the repaired Numbers chapter, a rendered validated XHTML frame, and a working original/validated toggle. |
| `make doctor`, `make fmt`, `make ci`, `cargo clippy -p corpora-convert --all-targets --all-features -- -D warnings` | Passed. |
| EPUB Ruff, Ruff format check, mypy, pytest, `uv build` | Passed; 36 tests, including guarded repair, lost-attribute and ambiguous-link rejection, deterministic repaired output and real loaders. |
| `make -C packages/tei-to-tf check build` | Passed; 138 tests, 11 skipped. |

The external Context-Fabric check created a derived `.cfm` cache; it was
removed afterward. `tf/assets/` is the only directory under the final `tf/`.
The browser page is a local QA aid. The repaired XHTML hierarchy is a parser
interpretation where the original markup was misnested, so this receipt proves
text, retained explicit tags/attributes, identifiers and loader behavior, not
that an invalid source had a unique intended tree.

## Semantic markup and reading view

Bundle format `corpora-epub-to-tf/2` retains 5,229,951 exact source character
slots while exposing 4,974,768 characters in the default reading view. A run
of layout spaces becomes one space, and a run containing linebreaks becomes one
linebreak; zero-width layout marks are omitted. Preformatted spans remain
exact. `T.text(node, fmt="text-source-full")` still returns the source string.
Each element and asset keeps source and reading offsets.

The full 2001 EPUB bundle at `target/qa-2001-semantic-v2/` has 72 EPUB3 TOC
entries and 12,230 classified reading links: 3,958 navigation and 8,272
reference links. Explicit source markup yields 1,947 headings, 71 subtitles,
33,415 verse-number elements, three tables, and one reading TOC section.
Navigation links require a TOC or chapter-menu ancestor; prose links are
references. Missing TOC members or fragments block export.

| Command | Result |
| --- | --- |
| `uv run --project packages/epub-to-tf epub-to-tf SOURCE target/qa-2001-semantic-v2 --checker target/debug/corpora-epub-check --repair --max-slots 8000000` | Passed; `SOURCE` is the original iCloud EPUB path above. |
| `uv run --project packages/epub-to-tf --group dev python target/qa-2001-semantic-verify.py target/qa-2001-semantic-v2` | Independently parsed 73 original XHTML bodies, checked raw text and a separate regular-expression reading projection, and checked both Text-Fabric formats through Context-Fabric. |
| `python3 /Users/emmanuel/.codex/skills/text-fabric-validator/scripts/tf_validate.py target/qa-2001-semantic-v2/tf --json target/qa-2001-semantic-v2-validation.json --report target/qa-2001-semantic-v2-validation.md --quiet` | Zero errors; TF064 warns about intentionally blank layout slots and TF065 records the no-invented-separators policy. |
| `uv run --project packages/epub-to-tf --group dev python packages/epub-to-tf/tools/qa_browser.py target/qa-2001-semantic-v2 target/qa-2001-browser` | Passed. Aside Browser at `http://127.0.0.1:8771/index.html?schema=2` showed dark background, 73 documents, 72 TOC entries, exact source/reading status for Numbers, semantic counts, and a working TOC jump to Genesis. |
| EPUB Ruff, format check, mypy, pytest, `uv build` | Passed; 42 tests, including semantic roles, link kinds, nested EPUB3 TOC, NCX fallback, broken TOC targets, whitespace and a blank reading item. |
| `make fmt`, `make ci`, `cargo clippy -p corpora-convert --all-targets --all-features -- -D warnings` | Passed. |
| `make -C packages/tei-to-tf check build` | Passed; 138 tests, 11 skipped. |

The earlier full bundle remains under `target/qa-2001-bundle/` for comparison.
Neither generated bundle is tracked by Git. The browser page reports a display
projection; the original archive and exact member text remain available for
source-faithful work. The external loader's derived `.cfm` cache was removed;
`tf/assets/` is the final bundle's only directory under `tf/`, and all 351
checksums match.
