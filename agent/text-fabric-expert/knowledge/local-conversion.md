# Local conversion, quality and reviewed changes

Read the relevant package README and actual CLI `--help` before execution. Commands
below run from the repository root unless a working directory is stated. Uppercase
`SOURCE`, `NEW_DIR`, `BUNDLE`, `SITE`, `NODE`, `START`, `END`, `RESOLUTION_ID` and
`REPLACEMENT` are task-specific values, not defaults. Obtain node/offset values
from the actual loaded corpus. All output directories must be new and outside sources.

These are implemented, bounded local routes, not universal format support. The Rust
`corpora-convert` EPUB validator and `corpora-pdf` extractor are working components,
not placeholders; the Python packages orchestrate their TF exports. Inventory with
`python3 agent/text-fabric-expert/configure.py doctor`; it neither installs nor runs
converters. Rebuild after source changes: existence does not prove artifact freshness.
Dependency/build commands may download locked dependencies; review network policy first.

## TEI → TF

Sources: `packages/tei-to-tf/README.md`, `src/tei_to_tf/cli.py` in that package.

```sh
uv run --project packages/tei-to-tf tei-to-tf --help
uv run --project packages/tei-to-tf tei-to-tf SOURCE --output NEW_DIR
make -C packages/tei-to-tf check build
```

Use explicit `--choice original|edited` and `--apparatus lemma|witness` only with an
approved editorial policy (`--witness '#A'` for an exact witness token). Defaults
reject ambiguous readings. `--notes separate` retains note XML outside reading
slots; `--notes include` includes it in the stream. Metadata and explicit TOC are
not reading text. Preserve original bytes, excluded readings, source IDs and hashes.
Slots are Unicode scalars, not words: mixed content/tails, combining marks and spaces
must survive the selected projection without invented separators. XML-mandated
entity/line-ending normalization is distinct from byte preservation.

`--schema` accepts a local self-contained RNG/XSD; discovery is not validation.
DTD-dependent inputs, XInclude, `copyOf`, `spanTo`, nonempty `standOff`, `sourceDoc`
reading order and unsupported transcription/virtual text require a dedicated adapter
and fail closed. Generic XML is not automatically TEI. Defaults cap 1,000 acquired
files, 64 MiB/file, 256 MiB total, 1,000,000 slots and 10,000,000 memberships. Public
remote acquisition is a separate explicit choice; private/gated repositories and
embedded Parquet/JSON datasets are not supported. Prefer supplied local sources.

## EPUB → TF

Sources: `packages/epub-to-tf/README.md`, `src/epub_to_tf/__init__.py` in that package;
`crates/corpora-convert/README.md` and `src/bin/epub_check.rs` in that crate.

```sh
cargo build -p corpora-convert --bin corpora-epub-check
uv run --project packages/epub-to-tf epub-to-tf --help
uv run --project packages/epub-to-tf epub-to-tf SOURCE NEW_DIR --checker target/debug/corpora-epub-check
cargo test --locked -p corpora-convert
uv run --locked --project packages/epub-to-tf pytest -q packages/epub-to-tf/tests
uv run --project packages/epub-to-tf python packages/epub-to-tf/tools/qa_browser.py BUNDLE SITE
```

The Rust checker validates a local unencrypted reflowable EPUB and linear spine;
blocking findings prevent export. `--repair` is opt-in, limited to audited XHTML
recovery and unreferenced duplicate-ID repair, with original/repaired archives,
initial/final diagnostics and a repair ledger. It never clears ambiguous inbound
references or structural findings through spelling/AI. Defaults: 80 MiB archive,
1,024 members, 16 MiB/member, 64 MiB expanded total and 1,000,000 slots;
`--max-slots` can explicitly raise slots to at most 8,000,000. Encryption, non-linear
spine, unsupported layout/media, scripts/iframes and unsafe paths remain blockers.

Check both projections: `T.text(node)` is the display reading; explicit
`T.text(node, fmt="text-source-full")` is the exact source projection. Preserve
`text.tf`, original archive, spine order, source/reading offsets, notes, `noteref`
edges, links and content-addressed assets. Zero-length EPUB elements are anchored
to adjacent slots; their authoritative spans have `start=end`, so `T.text()` on the
anchor is not their content. The semantic QA page is a visual aid, not original CSS
reconstruction or a substitute for loader/fidelity checks. Opaque media preservation
does not imply playback support or transcription.

For full Python lint/types/build checks, run these **from `packages/epub-to-tf`**:

```sh
uv run --locked --group dev ruff check .
uv run --locked --group dev ruff format --check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
uv build
```

## PDF → TEI → TF

Sources: `packages/pdf-to-tf/README.md`, `src/pdf_to_tf/cli.py` in that package;
`crates/corpora-pdf/src/bin/pdf_extract.rs`.

```sh
cargo build -p corpora-pdf --bin corpora-pdf-extract
uv run --project packages/pdf-to-tf pdf-to-tf --help
uv run --project packages/pdf-to-tf pdf-to-tf SOURCE --output NEW_DIR --extractor target/debug/corpora-pdf-extract --languages eng
make -C packages/pdf-to-tf check build
```

Requires Poppler, Tesseract and every requested language model; select actual source
languages with `--languages` and optional `--tessdata`. Defaults limit 200 pages.
Keep the strict default score > 0.95: equality fails. Do not lower `--min-score` or
use `--no-visual-check` to obtain a nominal pass. The score is OCR confidence or
text-layer/OCR agreement, **not transcription accuracy**. Review rendered pages,
columns/reading order, tables, headers, glyphs and diacritics before trusting slots.
Script risk does not prove exactly which marks are missing; require image evidence.

The pipeline retains extraction and PDF bytes, builds TEI with `--notes include`,
`--milestones pages` and `--facsimile zones`, then checks every line, word and page
through the real TF loader against extraction. This proves extraction-to-TF fidelity,
not that extraction matches the image. TF lives under `NEW_DIR/tei-to-tf/tf`.
Read `conversion-report.md` and the full JSON: exit 3 is gated (no TEI/TF), exit 1 is
verification failure, exit 2 is operational error. Exit 0 can mean
`converted_with_issues`; review those issues. Images/charts are not transcribed,
complex tables and multi-column reading order remain bounded/heuristic. Schema
validation needs `--schema`; no automatic hosted OCR fallback is enabled.

## Three independent acceptance gates

1. **Static:** run the installed validator's `tf_validate.py` on the actual `tf/`
   directory, saving Markdown and JSON outside the corpus. Inspect all blocking
   findings; explain corpus-specific warnings rather than suppressing them.
2. **Real loaders:** cold-load staged `.tf`-only copies with Text-Fabric and
   Context-Fabric, check text, section/locality behavior and edge values, then warm
   reload. Record versions and observed results; no stale caches or corpus app code.
3. **Source fidelity:** compare every document's exact selected source text and
   applicable spans, notes, references/assets, metadata and ID mappings. Use image
   review for PDF extraction. Preserve loss/repair ledgers and unresolved findings.

```sh
python3 "$TF_VALIDATOR/scripts/tf_validate.py" "$CORPUS" --report validation.md --json validation.json
```

Set `TF_VALIDATOR` to the installed validator skill; `CORPUS` is the actual TF root.
The TEI and EPUB exporters already check internal TF text round trips; their tests
also exercise real TF/CF loads. Still report which checks ran on the user's bundle.
The word-slot `tf_reconcile.py` is **not a character-slot oracle** for these converters.
Do not compare word counts to character slots or apply its word-based append patches.
Use exact text/span assertions and real loaders instead. TF064/TF065 whitespace and
missing-separator notices can be expected for character slots; inserting spaces to
silence them corrupts fidelity. A clean static report or load alone is not acceptance.

## Optional native and hosted quality review

Sources: `crates/corpora-core/README.md`, `packages/tei-to-tf/README.md` quality
sections, `packages/quality-ai/README.md`, `package.json` and `bridge.ts` there.

```sh
cargo build --locked -p corpora-core --features spellcheck --bin corpora-text-check
cargo test --locked -p corpora-core --all-features
npm ci --prefix packages/quality-ai
npm run check --prefix packages/quality-ai
npm run build --prefix packages/quality-ai
npm test --prefix packages/quality-ai
```

Use existing pinned dictionaries; if installation is authorized, the documented
installer is `python3 crates/corpora-core/tools/install_dictionaries.py --output target/cspell-dictionaries`.
It downloads data and refuses existing output. The doctor never invokes it.
Enable native QA with `--quality-engine target/debug/corpora-text-check
--dictionaries target/cspell-dictionaries`. Set corpus `--locale` independently of
`--metadata-locale`; language uncertainty and structural blockers cannot be cleared
by guessed language or spelling AI. Old native binaries fail closed; rebuild them.
Validate, repair separate copies, and revalidate; retain originals and all receipts.
Corpus wording is never automatically changed. Red non-corpus findings remain blocked
without required review; correction maps do not bypass AI/dictionary validation.

The optional bridge is TypeScript on Node 22+, compiled to
`packages/quality-ai/dist/bridge.js`, not a source `.ts` file or legacy `.mjs` entry.
`npm install` and `npm ci` automatically compile the bridge through
`prepare: npm run build`, unless lifecycle scripts are disabled. Use the explicit
build above after source changes or when installation scripts were disabled.
Only after explicit authorization to transmit source excerpts/findings, use
`--ai-bridge packages/quality-ai/dist/bridge.js`, an explicitly chosen `--ai-model`,
and `--ai-max-requests` plus `--repair-cycles`. `AI_GATEWAY_API_KEY` belongs only in
the process environment, never reports or browser assets. Explain provider/data
scope, costs and retention policy before any call. A request cap is not a dollar
budget; credentials or free credits are not consent. No automatic hosted fallback.
The model proposes only; exact-span checks and full local revalidation own acceptance.
Offline SDK mocks are unit tests, not live provider/model acceptance.

## Existing TF AI resolver: propose, review, apply

Sources: `packages/tf-ai-resolver/README.md` and `src/tf_ai_resolver/cli.py` there.

```sh
uv run --project packages/tf-ai-resolver tf-ai-resolver --help
uv run --project packages/tf-ai-resolver tf-ai-resolver inspect BUNDLE/tf NODE START END --text-feature text
uv run --project packages/tf-ai-resolver tf-ai-resolver resolve BUNDLE/tf request.json NEW_DIR
uv run --project packages/tf-ai-resolver tf-ai-resolver apply NEW_DIR RESOLUTION_ID REPLACEMENT APPLIED_DIR
uv run --project packages/tf-ai-resolver tf-ai-resolver serve BUNDLE/tf SITE RESOLUTIONS --port 8772
```

Build `request.json` from `inspect` output plus `mode` (`fix`, `suggest`, `custom`)
and `prompt`; see the README wire example. Select the actual text feature/format,
exact SHA-256 revision, expected text and zero-based half-open Unicode scalar offsets.
Selection limit: 4,096 characters; prompt: 1–2,000; context: at most 500 each side.
Do not invent node IDs/offsets. Every resolution starts `proposed`; apply only after
review of the exact replacement/reason with `expected_replacement` (the CLI's
`REPLACEMENT`). Each proposal/application writes a new bundle and reloads TF/CF.
Applied text lives in `F.resolved_reading.v(node)`; `T.text(node)` and source slots
remain unchanged. Structural/asset edits are unsupported: return `no_change` with
reason. Re-inspect after an overlay changes the bundle revision.

The QA service binds to `127.0.0.1`, enforces same-origin JSON and session proposals;
it is not a public API. **Local loopback does not mean local inference**: resolve
uses the configured Codex provider and transmits selection/context. Obtain explicit
authorization before resolve or a browser model action; starting the UI is not
permission to send text. No hosted transmissions without authorization, including
quality-ai, the resolver, OCR fallback and external plugins.

Run full checks **from `packages/tf-ai-resolver`** (offline tests use fake experts):

```sh
uv run --locked --group dev ruff format --check .
uv run --locked --group dev ruff check .
uv run --locked --group dev mypy src
uv run --locked --group dev pytest -q
uv build
```

## Shared model changes and unsupported routes

Shared model work must edit `crates/corpora-core/schema` first (`model.json` and/or
`domains/*.json`), then run the root commands in order:

```sh
make types
make types-check
```

`make types` regenerates **all Rust, TypeScript, Swift and SQL** outputs;
`make types-check` rejects stale, missing or extra generated files without modifying
them. Both targets skip when `crates/corpora-typegen/Cargo.toml` is absent.
Do not hand-edit generated targets or create parallel one-language models. Read
`crates/corpora-core/schema/README.md` for the contract. `make ci` includes
`types-check` and `agents-test`; run `make types` separately after schema changes.
This guide does not assume an additional aggregate conversion Make target.

Markdown, generic XML, USX, DOC/DOCX and TF → SQL/XML/graph still need explicit,
verified adapters and loss policies; the TEI/EPUB/PDF commands do not implement them.
DOC is not DOCX; USX milestones and overlap need vocabulary-specific interpretation.
Inspect APIs/help before claiming support. Keep deterministic unit/static drift
tests distinct from actual per-corpus conversion, loader/image checks and live
host-agent/model acceptance; report each layer separately.

Run the offline bundle verification from the repository root:

```sh
make agents-test
make agents-check
```

`make agents-test` runs the deterministic unittest suite, or skips when
`agent/text-fabric-expert/tests` is absent. It does not invoke converters, loaders
or models. `make agents-check` validates canonical agent assets. Both are included
in `make ci`; neither establishes live model acceptance.
