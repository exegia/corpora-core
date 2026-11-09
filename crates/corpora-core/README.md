# corpora-core

Core types and traits for the Corpora apps suite.

## Overview

This crate provides shared abstractions used across:
- Conversion runners
- Text-Fabric builder  
- Model typings generation
- Data sources
- AI skills and agentic workflows

## Usage

```rust
use corpora_core::{Error, Result};

fn process_document() -> Result<()> {
    // Your processing logic here
    Ok(())
}
```

## Features

- `serde` - Enable serialization support for core types
- `spellcheck` - Enable the Matchum spelling engine and JSON-lines bridge (dictionary data installed separately)

## Shared structural and spelling diagnostics

Rust callers can check XML directly without Python, dictionaries, or the `spellcheck`
feature. `structural::check_xml` uses a strict namespace-aware parser with no recovery,
DTD loading, external entity resolution or network access:

```rust
use corpora_core::structural::check_xml;

let source = "<root><title>Example</Title></root>";
let report = check_xml("edition.xml", source)?;
assert!(!report.passed());
let proposal = &report.diagnostics[0].suggestions[0].edits[0];
assert!(proposal.matches_source(&report, source));
assert_eq!(proposal.after, "</title>");
# Ok::<(), corpora_core::Error>(())
```

With `spellcheck`, use
`SpellEngine::check_diagnostics(source_id, text, role, locale_hint)` for the same
`diagnostic::DiagnosticReport` type. `SpellEngine::check` and its existing JSON shape
remain unchanged. Spelling coordinates refer to the exact supplied **decoded text
segment**, not to raw XML; callers must retain the segment-to-document mapping.

The version-1 shared contract includes caller-supplied source identity, a SHA-256 of
the exact UTF-8 input, issue code/category, explanation, certainty, severity,
blocking status, optional policy score, locations and suggestions. Locations contain
zero-based UTF-8 byte and Unicode scalar offsets and one-based line/scalar columns.
Ranges are half-open; LF starts a new line and CRLF is retained in offsets. Multiple
locations support related findings such as duplicate IDs. Empty locations explicitly
mean the parser cannot supply an exact location; no synthetic line 1 is advertised.

Suggestions include an explanation, `automatic` or `review` applicability, and zero
or more exact before/after edits. Empty edits mean guidance rather than a defensible
replacement. `automatic` permits an automated **attempt under caller policy**, not
unconditional approval. Dictionary misses remain possible issues, even when policy
scores them 90; scores are never confidence percentages. Structural parser/policy
failures are certain findings, but their proposed remedies can still require review.

The core never applies these edits. The API layer checks `TextEdit::matches_source`,
rejects overlapping/conflicting edits, applies a chosen candidate to a separate copy,
then reruns all required validation. Recheck after every batch: every edit in a report
uses the unchanged source snapshot. Retain originals and record decisions, including
legitimate names/spellings accepted by contextual review. Corpus spelling candidates
always require contextual assessment; no corpus rewrite is automatically approved.

`check_xml_with_options` sets byte/node limits (defaults 64 MiB / one million nodes).
Set `StructuralOptions { tei: true, ..Default::default() }` to additionally check TEI
root/namespace, duplicate `xml:id`, XInclude, `copyOf`/`spanTo`, and selected unsupported
transcription/stand-off adapter boundaries. Namespace-free TEI needs explicit opt-in.
These are bounded adapter checks, **not full TEI P5/RNG/XSD validation**, editorial
reading selection, or conversion parity with the Python package. Clean structural
reports do not imply that conversion, schema checks or spelling will pass.

The XML parser reports the first syntax error; repair and revalidation can reveal
further errors. Case-only closing-tag mismatches expose an exact candidate correction;
ambiguous mismatches and undefined entities provide guidance. Malformed ampersands
offer a review candidate because a broken entity reference may need a different fix.
Comments, CDATA, processing instructions and valid references are parsed as such.
Inputs must already be decoded to UTF-8; hashes cover those bytes, not an earlier
file encoding. Original-source acquisition, projection, schema validation and repair
orchestration still live in Python and can migrate independently.

```sh
cargo test --locked -p corpora-core --no-default-features
cargo test --locked -p corpora-core --all-features
```

## License

MIT OR Apache-2.0


## Language and spelling

### Purpose-aware TEI dates and identifiers

`purpose::validate_tei_metadata(source_id, xml, expected_document_id, allow_no_namespace)`
works without dictionaries or the `spellcheck` feature. It returns the shared,
source-hashed diagnostics plus `PurposeField` receipts for recognized metadata fields:

```rust
use corpora_core::purpose::validate_tei_metadata;

let xml = "<TEI xmlns='http://www.tei-c.org/ns/1.0'><teiHeader><date>2014</date></teiHeader></TEI>";
let result = validate_tei_metadata("edition.xml", xml, None, false)?;
assert!(result.report.passed());
assert_eq!(result.fields.len(), 1);
# Ok::<(), corpora_core::Error>(())
```

Only qualified TEI `date`/`idno` elements within metadata scopes are routed this way;
reading-text and foreign-namespace fields are left to their existing checks.
Namespace-free TEI requires explicit opt-in. Nested child markup is blocked rather
than flattened into a structured value. Original XML ranges (UTF-8 bytes, scalars,
line/column), decoded values, zero-based element-child locators and validation status
are retained. `policy_version`, `expected_document_id` and `allow_no_namespace` bind
the receipt to the caller's policy as well as its source snapshot.

The bounded date policy accepts nonzero four-digit years, ordered numeric year ranges
(`1868-1873` or an en dash), `YYYY-MM` and valid `YYYY-MM-DD` Gregorian dates. It checks
`when`, `from`, `to`, `notBefore` and `notAfter` for valid forms and a consistent
interval, including consistency with text at its stated precision. Missing values,
invalid leap days, reversed/conflicting bounds, unsupported text, explicit calendar/
dating-system attributes and ISO/custom dating extensions remain blocked. A bounded
numeric date check is not full TEI schema validation or historical fact verification.

Identifier expectations are supplied by the caller; core never derives one from a
filename. An expectation applies only to an untyped primary
`TEI/teiHeader/fileDesc/publicationStmt/idno` in a single root TEI document. Values are
trimmed for comparison, must be nonempty and have no internal whitespace. Typed IDs
(including ISBN), other scopes and collection-member IDs need a dedicated policy and
remain blocked. A mismatch is evidence of inconsistency with the caller's expectation,
not proof that the source is wrong. Suggestions require review of the expectation and
references and contain **no automatic identifier edits**.

The JSON-lines bridge supports this operation without loading dictionaries:

```json
{"operation":"purpose","source_id":"edition.xml","expected_document_id":"edition","text":"<TEI xmlns='http://www.tei-c.org/ns/1.0'><teiHeader><date>2014</date></teiHeader></TEI>"}
```

Rebuild `corpora-text-check` before using the Python adapter with the new operation.
The adapter checks complete field coverage, policy/source bindings and all coordinates
before excluding typed fields from language/spelling. Every final candidate is checked
again; failed purpose findings cannot be cleared by spelling AI or correction maps.

`language::detect_language(text, locale_hint)` returns the selected locale,
confidence, detection method, allowed cspell dictionary directory, alternatives,
and whether the region is a default. Unknown/short or unsupported text does not
silently select English. Generic `en` defaults to `en-US`; use `en-GB`/`en-CA`
for a regional choice. French defaults to traditional `fr_FR`; `fr-FR-1990`
selects `fr_FR_90`. Ancient Greek requires `grc`; statistical Greek detection
cannot reliably distinguish historical periods. `en_shared` and `public-licenses`
are supplemental resources, not languages.

The optional `spellcheck` feature exposes `SpellEngine`, backed by the published
Matchum dictionary crate 0.0.1. This crate requires Rust 1.91. Dictionary data is
installed separately; it is not embedded or fetched during library calls.

```sh
python3 crates/corpora-core/tools/install_dictionaries.py --output target/cspell-dictionaries
cargo build --locked -p corpora-core --features spellcheck --bin corpora-text-check
```

The installer uses `tools/dictionaries.lock.json`: pinned npm versions and SHA512
archive integrity, plus a commit/SHA256 pin for unpublished `en_shared`. It executes
no npm scripts and retains license files shipped by packages. Add repeated
`--dictionary en_US` options for a subset. Existing install directories are refused.
The runtime validates each artifact's SHA256 and supports cspell TrieXv3/text/gzip,
case sensitivity, forbidden-word policy, and replacement maps. It does not claim
full cspell CLI/config or weighted-suggestion parity. Only the 15 requested
resources are allowed; Canadian config references outside that list are not loaded.

The JSON-lines executable accepts one request per line on stdin and writes one
response per line. Default requests without a dictionary directory detect only.
With the directory argument it lazily loads the selected language dictionary:

```json
{"text":"hello world","locale":"en-US","role":"corpus"}
```

Structural requests use the shared version-1 report and need no dictionaries:

```json
{"operation":"structure","source_id":"edition.xml","text":"<title>Example</Title>"}
```

The structural operation works with or without a dictionary directory. Requests
without `operation` retain the existing detection/spelling response shapes. Python's
quality/preview adapter consumes these Rust reports, verifies their source hashes
and coordinates, and rechecks each repaired candidate through core. It fails closed
with an older executable that lacks the versioned structural operation.

`role` is `corpus`, `metadata`, `frontmatter`, `footnote`, or `additional`.
`detect_only: true` requests just the language payload even with dictionaries
configured. Errors are JSON objects with `error`; callers must check them.
Optional `supplements: ["en_shared", "public-licenses"]` loads those resources too;
shared English words apply only to English. Library callers can select them with
`SpellEngine::load_selected`.
All diagnostic offsets are **Unicode scalar offsets within the supplied text**.
Scores are policy severity, not confidence probabilities:

| Finding | Score | Pass | Repair |
| --- | --- | --- | --- |
| Heading, all-caps or initial capital | 20 | Yes | Flag and ignore |
| Other corpus spelling / suspicious typography | 60 | Yes | AI suggestion; no automatic corpus edits |
| Other non-corpus spelling | 90 | No | Core supplies dictionary candidates; quality pipeline requires AI review and revalidation |

Literal source text cannot invoke cspell directives. Every occurrence is checked.
Capitalized words can match lowercase dictionary entries without changing the text.
The engine never applies its replacements itself; the converter owns the audited
repair/revalidation passes. Proper names and ambiguous suggestions are not silently
rewritten. For the converter workflow see `packages/tei-to-tf/README.md`.


### Large compressed dictionaries

Matchum 0.0.1 expands TrieXv3 shared nodes into a hash dictionary. The pinned Hebrew, Italian and Latin
resources represent about 107 million, 45 million and 19 million terminal paths,
respectively. `compact_trie.rs` adapts Matchum's MIT-licensed parser and
implements its public `Dictionary` interface while retaining the shared trie.
Exact lookup is bounded by word length; suggestions use bounded single-edit
dictionary-alphabet candidates rather than scanning the expanded word set. These suggestions are
not identical to Matchum's ranked full-dictionary suggestions. The original license
and pinned upstream attribution are retained in `tools/MATCHUM-LICENSE` and source.
The adapter is limited to these three resources and rejects unsupported compound
or suggestion metadata; other dictionaries use Matchum's
published loaders, configuration maps and suggestion implementation.
