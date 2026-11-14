# Workflows and capability boundaries

## Discover, read and analyze

Prefer Agora's Context-Fabric plugin: list_available_corpora →
describe_available_corpus → list_collection_members for collections →
prepare_corpus → inspect load_preflight → load_corpus. For local TF use
install_local_corpus, which snapshots sources; then use returned identifiers.
Preserve source_revision and ordered-last-wins module order. Inspect active_loads
before retrying a cold compile. Inspect actual tool schemas; names and parameters
vary with installed versions. Use corpus_cache_status and cancellation deliberately.

Discover node types, features, edge direction/value types, sections and text formats
before query construction. Load only required features. Use F/Fs for node features,
E/Es for edges, L for locality, T for text/sections, N for canonical walking and S
for structural search. Do not assume BHSA lemma, morphology or section conventions.
For concordance, frequency, co-occurrence, collocation or TF-IDF specify units,
normalization, window, denominator and comparison population before calculating.
Inspect missing values and spot-check returned nodes/passages. Cache-size limits
are not corpus cardinalities: cfabric-mcp 0.1.7 capped counts; inspected 0.1.8 code
returns total_count separately from cached_count/results_truncated. Verify version.
Cross-corpus ontology correspondences (ontoTF) do not prove token identity.

## Validate and reconcile

Use the installed text-fabric-validator scripts; do not copy an unlicensed local
skill into a distributable bundle. Set TF_VALIDATOR to its verified skill directory.

```sh
python3 "$TF_VALIDATOR/scripts/tf_validate.py" "$CORPUS" --report validation.md --json validation.json
python3 "$TF_VALIDATOR/scripts/doc_schema.py" "$SOURCE" --json source-schema.json
python3 "$TF_VALIDATOR/scripts/tf_reconcile.py" "$CORPUS" --schema source-schema.json --help
```

Read --help and the validator skill before selecting explicit level mappings and
report paths. Inferred mappings require evidence; do not bypass its confirmation
with --yes on an unseen corpus. Static warnings may encode corpus-specific
assumptions. Check the official format and real runtime before diagnosing corruption.
Test implicit node numbering/ranges, escaping, UTF-8, scalar values, valued/unvalued
edges, complete otype, slot-prefix numbering and nonempty valid oslots. Verify
section containment, text-format feature references, overlap/discontinuity and
source annotation offsets. Keep static findings distinct from loader receipts.
Load only .tf source copies in temporary roots to avoid trusting stale binary caches.
Check exact reconstructed text, section lookup, locality and edge values, then reload.
CFR assertions apply only to an installed CFR-capable runtime; older CF uses .cfm.

## Convert and export

For implemented local TEI/EPUB/PDF converters, exact build/test commands, quality-ai,
reviewed resolver changes and shared schema generation, read
[local-conversion.md](local-conversion.md). Read each package README and actual CLI
help before executing. No hosted transmissions without explicit authorization.

| Input/output | Route | Required fidelity checks |
| --- | --- | --- |
| TF → TF / annotations | Official Fabric.save for feature updates; walker CV or corpora-tf for structural rebuild | Preserve all untouched features, node-ID mapping, edge targets, feature metadata and source provenance; reload staged output |
| TEI → TF | `uv run --project packages/tei-to-tf tei-to-tf SOURCE --output NEW_DIR`; text-fabric-factory for additional profiles | Namespaces, mixed content/tails, choices/apparatus policy, witnesses, standOff, overlap and Unicode scalar spans |
| Generic XML / USX → TF | Explicit vocabulary mapping to source model then walker/exporter | XML is syntax, not schema; USX book/chapter/verse milestones, notes, bridges and empty verses require a USX adapter |
| EPUB → TF              | `packages/epub-to-tf` with the Rust `corpora-epub-check` validator                                                                                                    | Exact source versus display projection, spine, notes/noteref, links, assets and source/reading offsets; optional audited repair then revalidation          |
| Markdown → TF          | Explicit document parser → source model → tested adapter                                                                                                              | Headings, whitespace, links and source locators; no bundled universal Markdown converter                                                                   |
| PDF → TF | `packages/pdf-to-tf`: corpora-pdf extraction, score gate (> 95%), TEI with pages/zones, `tei-to-tf --milestones pages --facsimile zones`, line/word/page verification | Score is OCR evidence, not accuracy; page references, columns/reading order, headers, tables, glyph and mark loss; no claim of lossless PDF reconstruction |
| DOC / DOCX → TF | Sandboxed office-format extractor → document model → exporter | Distinguish legacy binary DOC from DOCX ZIP/XML; preserve revisions, footnotes/tables where supported; report extraction losses |
| TF → XML / SQL / graph | Explicit export schema, official runtime data access | Overlap needs stand-off XML, many-to-many membership tables, valued edges, metadata and reversible ID mapping |

TEI, EPUB and PDF have bounded implementations in this repository; other entries
are routing recipes, not universal converters. Inspect adapter availability and
help/API before use. If absent, implement and test
a narrowly specified adapter within the authorized task or report the missing route.
MetaBook DocumentAnalysisResponse is a structural/count comparison, not a text-bearing
interchange format. Retain full source text and annotations separately. Its PDF
heuristics do not provide OCR or reliable tables. Keep schema version and error paths.

For corpora-tf, the Plan/TfBuilder layer owns deterministic .tf serialization;
Context-Fabric owns runtime/search/cache. Source metadata and annotations must survive
remapping. Inspect scripts/compatibility.py and examples/export_json.rs in the actual
sibling checkout before invoking those sibling-only tools. Here `corpora-convert`
implements EPUB validation and `corpora-pdf` implements PDF extraction; use the local
Python exporters rather than assuming these Rust components are universal TF writers.

## Edit/update protocol

Snapshot source hashes; stage a complete fresh dataset (never just changed WARP files).
Feature-only updates can preserve IDs; structural changes require rebuilding all affected
references. Missing text requires new slots, not merely appending section nodes.
Reject contradictory feature types, foreign references and ambiguous token alignments.
Produce a diff and source-to-output ID map, validate, load and reconcile the staged copy.
Publish or replace originals only when requested. Treat cache deletion as a separate action.

## Extend

Register a new adapter only with an input/output contract, dependency/version, license,
small fixture, loss ledger, determinism test and loader/source-fidelity receipt.
Use parameterized SQL and identifier allowlists. Do not copy historical exporters'
unsafe SQL or missing-metadata behavior. Dataset licensing is separate from code licensing.

## Observed runtime boundaries

The tiny smoke test uses a three-level book/chapter/verse section model. During
verification, Text-Fabric 13.1.2 sectionFromNode raised IndexError for the initial
one-level synthetic section fixture. This is not evidence that arbitrary section
models pass; add corpus-specific section fixtures before asserting compatibility.
The tested CF version was 0.5.8 with .cfm; no CFR acceptance is claimed here.

The local TEI/EPUB/PDF routes use character slots. The word-slot reconciler above
is not their fidelity oracle: use exact text/span checks and both real loaders as
specified in [local-conversion.md](local-conversion.md). Never insert separators or
apply word-based patches merely to silence character-slot warnings.
