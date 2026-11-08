# Verification — 2026-11-06

## Purpose-aware TEI dates and identifiers — 2026-11-08

Final acceptance: `target/qa-purpose-final-20261108-011818/acceptance-summary.json`.
The Rust `purpose::validate_tei_metadata` library API and dictionary-free bridge
`operation: "purpose"` now return source/policy-bound shared diagnostics and complete
structured-field receipts. Python consumes these on both initial and final snapshots.
Valid structured values bypass language/spelling; blocked values retain exact raw XML
locations and cannot be cleared by spelling AI or correction maps. No ID edits are
proposed automatically. Caller expectations are limited to the supported primary
untyped publication identifier; typed/collection IDs need another policy.

Fresh pinned 163-source run, with corpus `fr-FR`, original/lemma/separate-note policy,
no metadata override, no correction map and no hosted AI:

| Result | Count |
| --- | --- |
| Native metadata dates validated | 560 |
| Native primary identifiers validated | 154 |
| Inconsistent identifiers kept blocked | 2 |
| Original source hashes verified | 163 |
| Prepared files byte-identical to metadata-language baseline | 156 |

The two blocked values are `FDM-015-015-000-015` in `FDM-016-016-000-017.xml` and
`FDM-055-062-000-064-` in `FDM-055-062-000-064.xml`. Exact source ranges, decoded values,
caller expectations, policy versions and guidance remain in the receipts. Filename
disagreement establishes a caller-policy inconsistency, not authority to rewrite an ID.

Unresolved-language segments fell from 4,709 to 4,076; their groups fell from 126 to
125. Total reported blockers changed from 526 to 539: two explicit ID blockers and
12 additional dictionary findings exposed after metadata context changed, offset by
one resolved language group. All 163 documents remain quality-blocked. No source text
was changed and no uncertain language was silently approved.

Executed: `make fmt`, `make ci`, strict all-feature Clippy and `git diff --check`
passed. Core tests: **32 passed** with all features, **20 passed** without default
features. With the rebuilt optimized native bridge, dictionary data, external TF
validator and both pinned corpus caches configured,
`make -C packages/tei-to-tf check build` passed **137 tests, zero skips**, lint,
format, strict mypy and wheel/sdist builds.

Coverage includes valid/invalid leap days and intervals, date attributes conflicting
with text, unsupported calendars/markup, caller ID mismatches, typed/collection IDs,
foreign/reading scopes, namespace opt-in, Unicode/CRLF/entities/CDATA/comments, exact
raw coordinates, stale source/policy receipts, complete field coverage, purpose AI
exclusion, final-pass blockers and prose boundaries around empty structured elements.
The bounded Gregorian policy is not full TEI schema or historical date validation.
No new browser inspection or live hosted-AI evaluation was performed for this change.

## Independent metadata language — 2026-11-08

Final collection receipt: `target/qa-metadata-language-final-20261108-004245/acceptance-summary.json`.
All 163 inputs matched the pinned inventory at
`71fb49a3738a4533913327beffb39fd90633b0f1`. The run used the existing optimized Rust
engine/dictionaries, corpus locale `fr-FR`, original readings, lemma apparatus and
separate notes. No metadata override, correction map or hosted AI was used.

| Final-pass findings | Previous forced-corpus locale | Independent metadata selection |
| --- | --- | --- |
| Blocking spelling/typography findings | 4,805 | 387 |
| Unresolved-language groups | 0 | 126, retaining 4,709 affected segments |
| Structural/validation findings | 13 | 13 |
| Total reported blockers | 4,818 | 526 |
| Dictionary blockers for metadata `and`, `the`, `edition`, `by` | 1,808 | 113 |

All 163 documents remain quality-blocked; this is improved diagnosis and grouping,
not approval of uncertain language or proof every remaining dictionary finding is a
typo. Reliable selection chose English for 436 metadata segments and French for 749.
Unresolved groups retain every affected field/range and its original language evidence.
One grouped finding can represent many segments; the lower count does not erase
their uncertainty. All 163 originals were hash-verified, and all 156 prepared sources
had exactly the same SHA-256 as the preceding structural acceptance run.

With the native bridge, dictionaries, external validator and both cached-corpus
fixtures configured, `make -C packages/tei-to-tf check build` passed **120 tests with
zero skips**, Ruff lint/format, strict mypy and wheel/sdist builds. `make fmt`,
`make ci` and `git diff --check` passed. Tests cover local metadata hints and overrides,
empty-language resets, unsupported/unknown languages, separate collection contexts,
inline language transitions, whole corpus words across separate notes, exact grouped
locations, reform-French correction validation and actual native English metadata
checks under a French corpus policy. The repair-only native test now declares its
known English metadata explicitly rather than relying on a tiny unhinted header.

Implementation fingerprints are recorded in the final receipt. No Rust detector or
dictionary behavior changed. Browser inspection and hosted-AI evaluation were not
repeated for this policy change; the earlier structural/browser receipt below remains
separate. The initial ungrouped experiment is retained under
`target/qa-metadata-language-20261108-003601` and is not the final acceptance result.

## Rust structural adapter — 2026-11-08

### Full pinned collection and native browser acceptance

Fresh run: `target/qa-core-adapter-release-20261108-001542`. Its
`acceptance-summary.json` records implementation/binary SHA-256 fingerprints, source
revision, original hash checks, native rechecks, failed sources and diagnostic totals.
All 163 cached inputs matched their inventory SHA-256 at pinned revision
`71fb49a3738a4533913327beffb39fd90633b0f1`; all 163 retained originals matched too.

The offline quality run used the optimized `corpora-text-check`, the installed
dictionaries, explicit `fr-FR`, original spelling, lemma readings and separate notes.
No hosted AI or manual correction map was used. All 163 remained quality-blocked.
Final findings: 4,805 score-90, 371 score-60, 3,832 score-20 and 13 unscored structural
or validation diagnostics. These are policy/dictionary findings, not confirmed typos.
English metadata checked under the explicit French locale accounts for visible false
positives such as `and`, `the` and `edition`; general language/acceptance accuracy is
not established by this run.

One validated lexical repair changed `</respSTMT>` to `</respStmt>` in
`FDM-000-000-019-098.xml`, preserving the original bytes. The comparison rebuilt from
the quality receipts verified **156 / 163 documents and 247,871 character slots**;
seven remained rejected. Every accepted comparison source passed an additional
fresh Rust structural check. Exact text/spans and TF/CF cold/warm checks passed.
The raw static validator retained one TF064 whitespace error and one TF065 separator
notice, with the documented exact-scalar exception adjudication; no unconditional
static-validator or schema-validation pass is claimed.

With `CORPORA_TEXT_CHECK`, `CSPELL_DICTIONARIES`, `TF_VALIDATOR`,
`BAUDELAIRE_SOURCE` and `BAUDELAIRE_INVENTORY` configured,
`make -C packages/tei-to-tf check build` passed **109 tests with zero skips**, lint,
format, strict mypy and wheel/sdist builds. This includes the full unmodified-source
regression (155 / 163, 247,063 characters) alongside the corrected comparison above.

Safari opened the fresh offline `comparison/browser/index.html`. Both reading panes
and diagnostic layout were visually inspected in the existing dark appearance.
Filename/title filtering, next/previous navigation, a rejected source with no fabricated
TF view, remaining/applied pass selection and blocking-only filtering were exercised.
LA RANÇON showed 808 characters / 16 verses in both corrected panes, the exact
closing-tag edit and its native line/offset evidence. The browser remains on that
document. No browser security or appearance settings were changed.

An initial debug-engine run was interrupted for speed; its failed/partial receipt is
retained under `target/qa-core-adapter-20261108-001321`. It is not acceptance evidence.
No live hosted-AI evaluation, full TEI schema validation or CFR acceptance was run.

### Initial adapter checks

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

The full pinned collection and visual checks were still pending at this initial
adapter check; they are now recorded in the fresh acceptance section above. Live
hosted AI remains untested for this change. Older receipts below remain historical.

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
