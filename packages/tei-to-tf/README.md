# TEI → Text-Fabric converter

Convert TEI P5 documents from local files/directories, direct public HTTPS files,
GitHub repositories/tree/blob URLs, or Hugging Face model/dataset repositories.
The converter separates reading content from document and repository metadata,
retains original source bytes, and verifies TF text through the real loader.

## Run

From the repository root (uv manages Python 3.13 and pinned dependencies):

```sh
uv run --project packages/tei-to-tf tei-to-tf /path/to/edition.xml --output /new/output
uv run --project packages/tei-to-tf tei-to-tf /path/to/tei-directory --output /new/collection
uv run --project packages/tei-to-tf tei-to-tf https://github.com/OWNER/REPO --revision COMMIT --output /new/github
uv run --project packages/tei-to-tf tei-to-tf https://huggingface.co/datasets/OWNER/REPO --revision COMMIT --output /new/hf
uv run --project packages/tei-to-tf tei-to-tf source.xml --choice edited --apparatus witness --witness '#A' --output /new/reading
```

Multiple source arguments are accepted. Output must not exist. Repository branches
and tags resolve to commit IDs before downloading. For refs containing `/`, use a
repository-root URL plus `--revision`; tree/blob URLs otherwise treat one path
component as the revision. GitHub truncated tree listings fail explicitly. HF uses
the revision's complete `siblings` inventory. Private/gated repositories, archives
and dataset files embedded inside Parquet/JSON are not supported: provide local TEI.
The converter does not execute repository code or follow arbitrary manifest links.

## Content interpretation

| Input structure | Treatment |
| --- | --- |
| `teiHeader` | Full XML retained as metadata; work titles/authors come only from direct `fileDesc/titleStmt`, publishers/dates from `publicationStmt` |
| `teiCorpus`, nested `TEI`, grouped `text` | Collection headers remain distinct; each leaf `text` gets its own document identity and inherited collection metadata |
| `front`, `body`, `back` | Reading regions; prefaces, dedications and appendices remain corpus content |
| `titlePage`, `docTitle`, `docAuthor`, `docImprint` | Excluded from reading slots, retained with source path, XML, reason and boundary offset |
| `div/list type="toc"`, `contents`, `tableofcontents`, `table-of-contents` | Explicit TOC stored separately; no heuristic removal of similarly worded prose |
| `head`, divisions and mixed-content elements | Heading text stays in corpus; selected-reading headings and division hierarchy also form the outline |
| `note` | Separate XML by default; `--notes include` puts notes in the reading stream |
| Other element/attribute names | Generic element annotations, qualified attributes and parent edges; no invented schema-specific interpretation |
| Non-TEI XML, JSON/YAML/Markdown/text and schema files | Source manifest entries and original bytes, never reading slots |

This is deterministic structural interpretation, not an LLM guessing the genre or
meaning of arbitrary tags. A document's namespace, element inventory and schema
hints are recorded. Schema discovery **does not mean schema validation**. Supply
`--schema local.rng` or `--schema local.xsd` for validation with a self-contained
schema. Schema imports/includes and network schema fetching are refused.

## Fidelity and graph model

Slots are Unicode scalar characters, preserving decoded XML text, spaces, combining
marks, emoji, text/tail order and inline boundaries. This is not linguistic word
tokenization. XML parsing applies XML-mandated entity/line-ending normalization;
original source bytes retain their original encoding, declarations and spellings.
No spaces are invented between paragraphs, headings, regions or documents.
Formatting whitespace inside reading regions is preserved; layout whitespace outside
`front/body/back` is not corpus text. Non-whitespace text in skipped group boundaries
is an error rather than silent loss.

TF types are `character`, `document`, `region`, `block`, `element`. Navigation uses
`document/region/block`; blocks partition region content at top-level children and
leading text. These are navigation units, **not an inferred chapter schema**. Actual
TEI hierarchy is represented by element nodes and `parent` edges; `tei_tag`, qualified
attributes and source paths preserve arbitrary division depth. `manifest.json` maps
qualified attributes to queryable `attr_*` features. Local fragment links between
projected elements become `link_ref`, `link_target`, etc. External, unresolved,
excluded and zero-width targets remain explicitly listed with their original strings.

Whitespace-only document members are recorded as metadata-only and contribute no slots.
Empty elements/milestones retain exact scalar offsets in document JSON; no fictitious
characters or slotless TF nodes are created. Selected alternatives receive slots;
unselected readings remain in excluded fragments and the original source.

The official Text-Fabric writer creates feature files. A narrow normalization pass
removes its wall-clock `dateWritten` metadata and expands unvalued edge source IDs
for reproducibility and static-validator interoperability. The result is loaded again
and every document's exact text checked. Runtime caches are not shipped in the bundle.

## Outputs

| Path | Contents |
| --- | --- |
| `tf/*.tf` | Loadable corpus and annotations |
| `documents/ID.txt` | Exact selected reading text for each leaf document |
| `documents/ID.json` | Header metadata, regions, elements, source offsets, outline, excluded fragments and diagnostics |
| `sources/SHA256` | Every original acquired file, byte-for-byte |
| `manifest.json`, `checksums.json` | Input origins/revisions/classifications, policy, graph/attribute/ID maps, verification and artifact hashes |

Output is reserved exclusively and staged; ordinary failures remove the empty
reservation and staging data. A process kill can leave an empty reservation or hidden
staging directory, never a successful manifest. Existing sources/outputs are not
modified. Document IDs derive from source URI plus XML path, so moving a local source
changes its identity; output remains deterministic for the same sources and policy.

## Explicit boundaries

Ambiguous `choice` and `app` require policy selection. Original/edited supports
orig/reg, sic/corr and abbr/expan pairs; witness tokens match exactly. Missing or
multiple selected readings fail. `rdgGrp`, stand-off apparatus, substantive inter-branch
text and foreign-namespace alternatives are rejected.

DTD-dependent documents, XInclude, `copyOf`, `spanTo`, nonempty `standOff`, `sourceDoc`
reading order and transcription/virtual-text constructs (`subst`, `add`, `del`,
`restore`, `transpose`, `listTranspose`, `join`, `alt`) need dedicated adapters and
are rejected. Facsimile/header-only documents cannot yield reading text. Namespace-free
TEI requires `--allow-no-namespace`. The converter does not claim all TEI customizations
can be interpreted losslessly or that an unknown element's semantics are understood.

Defaults: 1,000 files, 64 MiB/file, 256 MiB acquired sources, 1,000,000 slots and
10,000,000 slot memberships. CLI flags can adjust these limits. Character graphs can
use substantially more memory than source bytes. HTTPS redirects receive public-IP
preflight checks and HTTP compression is refused. DNS preflight is not a network
sandbox against rebinding; isolate the process/network for hostile URLs. No remote
credentials are accepted. Remote schemas and linked entity URLs are never fetched.

## Verification

```sh
make -C packages/tei-to-tf check build
python3 "$TF_VALIDATOR/scripts/tf_validate.py" /new/output/tf --report validation.md --json validation.json
```

Tests cover metadata/TOC separation, exact Unicode and mixed content, collection
splitting, editorial branches, unsupported constructs, deterministic output across
writer dates, overwrite refusal, graph budgets, schema rejection, local/remote
acquisition contracts and actual Text-Fabric/Context-Fabric cold/warm loads.
The package workflow runs checks and a wheel build on PRs touching this package.

The installed text-fabric-validator is an external dependency, not vendored here.
Its TF064 whitespace and TF065 missing-separator notices are expected for character
slots: inserting separators would corrupt the source. Its reconciliation script
assumes a word per slot, so it is not a valid character-slot oracle. Exact fixture
text/span expectations plus both real loaders supply that boundary instead.

See [VERIFICATION.md](VERIFICATION.md) for actual runs and their limits.

### Baudelaire comparison QA

The pinned `LE COUVERCLE` regression converts the requested GitHub document and
compares every character, element span, verse and stanza against an independent
TEI parse through cold/warm Text-Fabric and Context-Fabric loads:

```sh
uv run --project packages/tei-to-tf python -m tei_to_tf.qa_baudelaire \
  --output target/qa-baudelaire \
  --validator "$TF_VALIDATOR/scripts/tf_validate.py"
python3 -m http.server 8765 --bind 127.0.0.1 --directory target/qa-baudelaire/browser
```

Use a new output directory for each run. Open `http://127.0.0.1:8765/index.html`
for side-by-side views, or `tei.html` and `tf.html` separately. These are lightweight
QA reading views: the TEI view uses the independent XML parse and the TF view uses
the actual loaded feature graph. The raw validator report and explicit adjudication
are retained in the browser directory; no schema-validation pass is claimed.

The optional regression test runs when `BAUDELAIRE_SOURCE` points to the cached
original source and `TF_VALIDATOR` points to the installed validator skill directory:

```sh
BAUDELAIRE_SOURCE=/path/to/cached/source.xml TF_VALIDATOR=/path/to/text-fabric-validator \
  uv run --project packages/tei-to-tf pytest packages/tei-to-tf/tests -q
```

### Full collection comparison

```sh
uv run --project packages/tei-to-tf python -m tei_to_tf.qa_collection \
  --output target/qa-baudelaire-all \
  --validator "$TF_VALIDATOR/scripts/tf_validate.py"
python3 -m http.server 8766 --bind 127.0.0.1 --directory target/qa-baudelaire-all/browser
```

Open `http://127.0.0.1:8766/index.html`. The default input is the complete
`CliffordAnderson/corpus-baudelaire/tree/master/fleurs-du-mal` directory; `--input`
also accepts a local directory or another supported repository URL. All XML files
are accounted for in the report and selector. Previous/next controls and title/file
filtering update both independent reading panes together; failures show the original
XML and diagnostics instead of a fabricated TF view. No repair is applied.

This collection QA profile selects **original spelling, lemma readings, separate
notes**. It covers nested divisions, headings, prose, verse, mixed content, qualified
attributes and parent edges, checking every document-local offset against the global
TF graph. Metadata and zero-width annotations are checked in the sidecars. It is a
body-only QA profile, not a promise of arbitrary TEI support. Ambiguous readings fail.
The CLI exits **1 for partial success**, retaining the complete navigable report;
exit 0 means every selected source passed. Schema validation is not performed.

For an offline pinned regression, set `BAUDELAIRE_INVENTORY` to the acquisition
cache's `inventory.json`, alongside `TF_VALIDATOR`, and run the package tests.
The inventory records each filename, origin, revision and SHA-256. This run's cache
is `target/qa-baudelaire-collection-input/inventory.json`; the live run tested 163
sources at revision `71fb49a3738a4533913327beffb39fd90633b0f1`.
`--cached-inventory /path/to/inventory.json` reuses and hash-checks that cache.

## Three-pass quality conversion

Structural diagnosis in quality mode now comes from the Rust core through
`corpora-text-check`'s `operation: "structure"` request. Rebuild the executable after
updating the crate; an old executable fails closed instead of falling back to Python
diagnosis. The plain converter still uses its existing Python parsing/projection path.
The native quality path accepts UTF-8 XML; other encodings need an explicit prior
conversion with original-byte provenance retained. Rust checks XML well-formedness;
Python still checks projection compatibility, editorial policy and any supplied schema.

Python applies only the existing bounded lexical fixes (bare-ampersand escaping and
case-only closing tags), checking the source hash, before text and byte/scalar/line
coordinates. Every intermediate candidate receives a fresh Rust report; no more than
32 lexical edits are attempted per preview. A partial failure returns the original
bytes and keeps the attempted edits as proposals. Core diagnostics, schema version
and source hashes are retained alongside the browser's existing receipt fields.
AI proposals and the final serialized spelling repairs must also pass core structural
checks before export. A preview passing structural checks is not spelling approval.

Programmatic collection previews using `run_collection(..., repair_structural=True)`
must pass `structural_checker=SpellProcess(path_to_executable)` and close that process
when finished. Loading an existing `quality_report` or running plain comparison does
not require a new native checker.

Build the core engine and install dictionary data using `crates/corpora-core/README.md`.
Enable the quality pipeline explicitly (the plain structural converter stays available):

```sh
uv run --project packages/tei-to-tf tei-to-tf /path/to/source.xml \
  --output /new/quality-output \
  --quality-engine target/debug/corpora-text-check \
  --dictionaries target/cspell-dictionaries \
  --locale fr-FR --choice original --apparatus lemma
```

1. **Validate:** retain original bytes, diagnose XML, prepare concrete structural
   repair proposals, detect language from body text/`xml:lang`, and run the Matchum
   process on textual content. The source is data, never cspell directives. Adjacent
   inline XML fields within a text block are checked as complete words. Metadata,
   frontmatter, notes and supplementary text receive the stricter spelling policy.
2. **Repair:** apply supported XML fixes and AI-reviewed non-corpus spelling corrections
   to separate copies. AI proposals are checked against exact source spans. Automatic XML
   edits are limited to closing tags and bare ampersands; deletion, text reconstruction,
   editorial reading choices and arbitrary schema rewrites remain blocked. Safe lexical
   fixes also work offline and are explicitly labeled as not AI-reviewed.
3. **Revalidate:** parse again, rerun spelling and TEI/schema checks. Restart on remaining
   blockers, up to `--repair-cycles` (default 3, maximum 10). Stop blocked on no progress
   or exhausted budget. Only documents without blocking diagnostics enter `corpus/`.

Spell scores alone use colors: **yellow 20** for headings or initial capitals (ignored,
nonblocking), **orange 60** for other corpus spelling/typography (AI suggestion only,
nonblocking), **red 90** for other non-corpus spelling (blocking until corrected).
Scores are policy severity, not probabilities. Structural issues have no numeric score.
The core's dictionary suggestions are not represented as AI suggestions.

For hosted review, install `packages/quality-ai` and supply `--ai-bridge
packages/quality-ai/bridge.mjs`. Configure `AI_GATEWAY_API_KEY` in the process environment.
See [hosted setup](../quality-ai/README.md). Without hosted AI, red findings stay blocked;
no corpus word is automatically rewritten. `--corrections` supplies candidates but does
not bypass AI review or dictionary validation.

Output includes `originals/`, `repaired/`, and `quality-report.json` with all three
pass receipts per cycle, before/after changes, hashes, locations and language evidence.
Validated documents are written to `corpus/`. Failed documents stay in the report;
the CLI exits 1 when any are blocked, and 2 for operational errors. Original files
are never overwritten. Repository README/manifests remain metadata, not XML failures.
Spell locations use Unicode scalar offsets in parsed text/tail fields; a diagnostic
spanning fields uses offsets in the named block's joined mixed content.

The explicit `--locale` overrides document hints; otherwise inherited `xml:lang`
controls each block, falling back to document detection. Short/unsupported language
requires a supported hint. Modern dictionaries are not proof that historical forms
are incorrect. No general-purpose automatic semantic repair or schema pass is claimed.

### Scored diagnostics in the comparison browser

Pass `--quality-report /path/to/quality-report.json` to
`python -m tei_to_tf.qa_collection` alongside its collection arguments. The browser
joins receipts by exact source origin and SHA-256, rejecting mismatched inventories.
When a quality report is supplied, the collection runner reads hash-verified repaired
copies from the quality report before building its comparison. Both panes then use the corrected XML,
with separate Original XML and Corrected XML links and an explicit repaired status.
Spelling blockers do not suppress a structurally valid preview; quality-approved
exports remain governed by the three-pass pipeline. Ambiguous structural issues
still fail. Calling the Python runner without `repair_structural=True` preserves
the original-source baseline QA mode.
It shows per-document initial findings, applied repairs and remaining issues, with
scores, roles, suggestions, source locations and a blocking-only filter. Structural
errors have no spelling score and display `N/A (structural)`.

The TF pane underlines findings in yellow (20), orange (60) or red (90).
Diagnostics appear in a collapsible right sidebar, closed on initial load. The
custom tooltip shares the underline's severity color; native title tooltips are omitted.
Hover or keyboard-focus a word to see the score, reason and suggestions. Mapping uses
the exact XML field and verified TF character range, never a document-wide word search.
Metadata, excluded variants and ranges that cannot be matched exactly remain in the
table. Underlines use pass 3 when displaying the repaired copy, or pass 1 for original
sources; they remain independent of the table's selected pass. Updated TF pages use content-versioned URLs to avoid stale iframe caches.

The two reading panes remain the original structural comparison, explicitly separate
from quality approval. A blocked quality run cannot be mistaken for an approved TF
export. Open `browser/index.html` directly from disk if HTTPS-only browser settings
prevent using a local HTTP server; all comparison assets and diagnostics are local.
For the local server use `http://localhost:8767/index.html`. Safari may require the
user to choose Continue on its HTTPS-only warning before allowing this HTTP origin;
do not disable HTTPS-only globally. This was verified after manual acceptance.

## Sources and reuse

Uses [lxml](https://lxml.de/parsing.html) for namespace-aware XML and the
[official TF writer](https://github.com/annotation/text-fabric/blob/ffa490aa9b678b28c6defb6e3909b89a31bada42/tf/core/fabric.py).
Classification follows [TEI text structure](https://tei-c.org/release/doc/tei-p5-doc/en/html/DS.html)
and [TEI headers](https://tei-c.org/release/doc/tei-p5-doc/en/html/HD.html).
Editorial rejection and provenance conventions follow the inspected existing Corpora
TEI implementation at revision `7ff9dbad81f3ed9a914ea826fce52deaa119b5ec`; that Rust
parser is in another checkout and is not silently substituted for this implementation.
No external skill scripts or corpus data were copied into the package.
