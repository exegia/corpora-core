# Verification — 2026-11-06

## Rust structural adapter — 2026-11-08

Python quality conversion and explicit collection repair previews now consume the
core's version-1 structural reports through `corpora-text-check`. Python's former
parser-message/regex diagnosis has been removed. Source acquisition, projection,
schema validation and guarded repair orchestration remain in Python.

Executed on this checkout:

- `make fmt`, `make ci`: passed, including all-feature Rust/Swift and automation checks.
- `cargo test --locked -p corpora-core --all-features`: 27 tests passed, including
  structural operation without dictionaries and unchanged legacy detection shape.
- `make -C packages/tei-to-tf check build`, with `CORPORA_TEXT_CHECK`,
  `CSPELL_DICTIONARIES` and `TF_VALIDATOR` configured: lint, format and strict mypy
  passed; **107 tests passed, 2 cached-corpus tests skipped**; wheel/sdist built.
- `git diff --check`: passed.

Real bridge acceptance checks sequential Unicode/CRLF ampersand and closing-tag
repairs, current-snapshot hashes/coordinates, undefined entity rollback, DTD refusal,
and successful quality conversion preserving original bytes. Real dictionary
repair/revalidation also passed. External-validator collection tests verify corrected
previews and that a core-blocked source stays failed and excluded while another
source exports and loads through TF/CF. Report fields retain raw core findings plus
the browser's existing before/after/repairable projection.

Regression tests reject stale/old bridge responses and inconsistent edit coordinates,
prevent Python parsing from bypassing core blockers, and require native revalidation
after AI candidates and serialized spelling repairs. Core requests report the first
XML failure; previews attempt at most 32 lexical edits and roll back partial failure.
The native quality path requires UTF-8 XML and a rebuilt bridge. Plain conversion and
existing quality-report consumption keep their previous dependency boundary.

The full pinned 163-source regressions, live hosted AI, and visual browser inspection
were not rerun for this adapter change. Earlier collection/visual receipts below are
historical evidence, not fresh acceptance of this revision.

## Executed

| Check | Result |
| --- | --- |
| `make -C packages/tei-to-tf check build` | 51 package tests passed; Ruff lint/format and strict mypy passed; sdist/wheel built |
| `make fmt`, `make ci` | Root Rust/Swift and template automation checks passed; nested Python is checked separately above |
| `actionlint .github/workflows/tei-converter.yml` | Passed |
| `git diff --check` | Passed |
| CLI conversion of `tests/fixtures/edition.tei.xml` | 1 document; 103 character slots; metadata and explicit TOC excluded |
| External `text-fabric-validator/scripts/tf_validate.py` | 0 errors; TF064 warning for whitespace slots, TF065 informational separator notice |
| Live GitHub blob URL | TEIC/TEI `P5/Test/testappinfo.xml` converted, 1 document / 1,434 character slots |

The GitHub run resolved `dev` to commit
`438e939fd2e64581fe39c349dcce49a97affcd9c`, then fetched the immutable raw file.
Source SHA-256:
`627342b2b460b715f08693bdb5ddbc3d88a8b02dfb3f5cb10bacb034d229fbcb`.
No upstream corpus fixture was vendored. The live output remains local at
`/tmp/tei-to-tf-live-github-20261106`; the synthetic static-validation output at
`/tmp/tei-to-tf-acceptance-explicit-20261106` (temporary artifacts may be removed by the OS).

## What the tests establish

Tests use Text-Fabric 13.1.2 and Context-Fabric 0.5.8. They check actual cold/warm
loads, section round trips, exact selected Unicode text and explicit source-range
expectations for nested annotations, parent/link edges and preserved raw bytes.
Determinism is checked with different injected writer dates, not just two builds
within one clock second. Source rejection/graph-budget failures leave no claimed
output. HTTP source-selection tests use fixed fake GitHub/HF API responses, pin
revisions, test truncated/missing inventories and enforce limits.

The static validator assumes word-like slots in two rendering checks. Whitespace
characters legitimately render whitespace, and `{text}` deliberately inserts no
separator between characters. Exact-text tests confirm these notices do not indicate
text loss for this model. Its word-shingle reconciliation script was not used as a
character-slot oracle; no reconciliation pass is claimed.

## Baudelaire QA follow-up

Converted `CliffordAnderson/corpus-baudelaire/fleurs-du-mal/FDM-000-000-000-087.xml`
at commit `71fb49a3738a4533913327beffb39fd90633b0f1`.
Source SHA-256: `d3ae54bc4775bc5efbc107f5ee63fbddf0b7a3b03a86b060a21f3874de8ce4b6`.
The local bundle is `target/qa-baudelaire`; no upstream source is vendored.

- Exact match: 904 character slots, 14 verses, four stanzas (4/4/3/3).
- Independent XML oracle checked every slot/rendered scalar, element span, stanza
  parent, title and section round trip through TF and CF cold/warm loads.
- Package lint, formatting and strict mypy passed. Default suite: 55 passed,
  one optional test skipped. With cached source and validator configured: **56 passed**.
- Separate TEI and TF HTML views and the side-by-side page were opened in Safari;
  both complete poems were inspected, including a side-by-side screenshot.

Raw static validation reports **one TF064 error** because its rendering heuristic
strips whitespace from character slots, plus a TF065 separator informational notice.
The QA report records `passed-with-proven-whitespace-exception`, retaining the raw
report and allowing only that error after exhaustive source/rendering equality.
There are no genuinely empty slots. No schema validation was performed.

## Complete fleurs-du-mal collection QA

Acquired all **163 XML files** from the GitHub directory at the same pinned commit
`71fb49a3738a4533913327beffb39fd90633b0f1`. Each source has an origin and SHA-256 in
`target/qa-baudelaire-collection-input/inventory.json`. Output is
`target/qa-baudelaire-all`, with navigable HTML in `browser/index.html`.

**155 documents passed; 8 were rejected**, without repairs. The emitted combined
TF corpus contains 247,063 character slots, 6,899 nonempty XML element annotations,
4,011 verse lines and 983 line groups. Another 218 zero-width annotations were
checked against the independent oracle in the JSON sidecars. Reading policy:
original spelling, encoded lemma, separate notes. This is not schema validation.

Seven rejected sources have malformed XML:
`FDM-000-000-012-000.xml`, `FDM-000-000-019-098.xml`, `FDM-000-102-000-126.xml`,
`FDM-066-096-000-120.xml`, `FDM-069-100-000-124.xml`, `FDM-078-109-000-134.xml`,
`FDM-081-000-003-000.xml`. `FDM-056-066-000-068.xml` has an apparatus entry
without a unique selected lemma. Every failure remains selectable in the browser
with its original XML and error. The collection CLI correctly exits 1 for partial
success; no all-source conversion success is claimed.

Every accepted document was independently checked for text/scalar rendering,
element inventory, spans, qualified attributes, parents, section round trips,
metadata fields and zero-width sidecars. Collection checks establish complete,
nonoverlapping slot coverage and no orphaned element nodes. Both TF and CF passed
cold and warm loads. Raw static validation has one TF064 whitespace error and one
TF065 informational finding; only TF064 is adjudicated after exhaustive scalar
equality, with raw evidence retained.

Package Ruff/format/strict mypy passed; **64 tests passed**, including the full
pinned collection regression with `BAUDELAIRE_INVENTORY`, the earlier single-source
regression with `BAUDELAIRE_SOURCE`, and external validation via `TF_VALIDATOR`.
Safari QA exercised next, previous, title search, filename search, failed-source
display, and both panes of a nested multi-section poem. The side-by-side layout
was visually inspected and left open at `http://127.0.0.1:8766/index.html`.

## Language and three-pass quality validation

The optional Matchum quality pipeline was verified locally on 2026-11-06:

- Root `make fmt` and `make ci` passed; the core crate ran 15 tests.
- `cargo clippy --workspace --all-targets --all-features --locked -- -D warnings`
  passed. Rust 1.91 is declared for Matchum compatibility but was not separately tested.
- The full Python suite passed **76 tests**, with `CORPORA_TEXT_CHECK`,
  `CSPELL_DICTIONARIES`, `TF_VALIDATOR`, `BAUDELAIRE_SOURCE` and
  `BAUDELAIRE_INVENTORY` configured. Ruff and strict mypy also passed.
- All 13 primary dictionary selections loaded; both supplemental dictionaries
  were exercised. Nine prose samples selected their expected languages. These
  smoke checks do not establish general language-detection or spelling accuracy.
- `actionlint .github/workflows/tei-converter.yml` and `git diff --check` passed.

Local evidence in `target/qa-quality-three-pass/quality-report.json` records a
successful conversion after repairing a bare ampersand, a case-mismatched closing
tag and metadata `helllo` to `hello`. Pass 3 has no diagnostics, original bytes
remain available, and TF output was emitted. Regression tests also cover blocked
corpus typos, ambiguous XML, unresolved metadata, mixed inline text, explicit TOC
classification and dictionary-verified repairs through the actual Rust process.

The separate `target/qa-quality-baudelaire/quality-report.json` deliberately remains
blocked: with explicit French locale, 24 metadata dictionary findings require
review, while the corpus word `Cythère` is a low-severity warning. Names, English
metadata and identifiers were not silently corrected. This quality run emitted no
TF corpus and did not alter the source body. It is distinct from the successful
structural conversion and browser comparison described above.

All dictionary artifacts remain local under `target/cspell-dictionaries`.
`target/dictionary-acceptance.json`, `target/dictionary-word-acceptance.json` and
`target/language-acceptance.json` contain the smoke-test receipts. Hebrew, Italian
and Latin use the documented compact Matchum dictionary adapter; full cspell CLI
or suggestion-ranking parity is not claimed.

## Scored collection browser follow-up

Re-ran the pinned 163-source collection: 155 structural comparisons passed and 8
were rejected, preserving the prior exact-text and TF/CF cold/warm checks. Results
are in `target/qa-baudelaire-scored`. A separate real-Matchum three-pass run at
`target/qa-quality-collection` blocked all 163 sources under the strict spelling
policy. It applied three repairs across three separate copies. Remaining findings:
8,397 score-90 non-corpus issues, 12 score-60 corpus issues, 597 score-20 warnings,
and seven unscored structural/validation failures. These are dictionary findings,
not proof of misspelling; multilingual metadata, identifiers and names need review.

The quality report was joined to the comparison by source origin and SHA-256.
Safari displayed the offline `browser/index.html`, both TEI/TF panes and the scored
diagnostic table with suggestions, language/dictionary and pass/filter controls.
HTTP access was blocked by Safari HTTPS-only mode; no security setting was changed.
The offline view was visually inspected. Interactive pass/filter transitions were
not separately exercised. Source/hash mismatch and safe diagnostic embedding have
regression tests. Full optional suite: **78 passed**; package Ruff/format/mypy,
root `make fmt` and `make ci` passed.

## Inline diagnostic follow-up

Generated 428 underlined word spans across the 155 verified TF pages. An independent
HTML read-back established that every article's text still equals its exact corpus
text. Regression tests cover repeated occurrences, Unicode offsets, tail fields,
stale findings, metadata exclusion, escaping and severity colors. Full optional
suite: **80 passed**; package Ruff/format/mypy and root `make fmt`/`make ci` passed.

Safari loaded `http://localhost:8767/index.html` after the user manually accepted
its HTTPS-only interstitial. Reload and navigation subsequently worked. The previous
claim that changing hostname alone fixed the restriction was not sufficient on refresh.
Content-versioned iframe URLs resolved stale cached TF pages. The orange underline
and visible score/reason/suggestion tooltip for `Banville` were inspected in Safari.
No global security setting changed. Underlines refer to original-source pass 1;
metadata and excluded variants remain in the table, without invented reading positions.

## Corrected structural previews

The collection CLI with `--quality-report` now rebuilds comparisons after supported
structural repairs, preserving original bytes and exposing corrected XML separately.
`target/qa-baudelaire-corrected` verifies **156 of 163 documents**, with 247,871
characters; seven sources still fail structural/reading checks. The additional
accepted source is FDM-000-000-019-098.xml, whose closing respSTMT tag was corrected
to respStmt. TF/CF cold/warm checks and the independent oracle passed. Safari showed
both corrected panes for LA RANÇON (808 characters, 16 verses), with the headline
“XML repaired; structure verified · Quality: blocked”. Spelling approval remains
separate. A regression verifies this behavior and original-byte preservation.

## Remaining limits

No live Hugging Face repository conversion was run; its adapter is covered by fixed
API-response tests. Live GitHub checks covered a blob URL and the complete 163-file fleurs-du-mal
directory, not an entire large repository. No large-corpus performance, full TEI P5 schema coverage, CFR runtime,
private/gated acquisition or unsupported transcription/stand-off acceptance is claimed.
GitHub-hosted CI has been added but not remotely executed; changes are uncommitted.
