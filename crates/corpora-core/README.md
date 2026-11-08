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

## License

MIT OR Apache-2.0


## Language and spelling

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
response per line. Without a dictionary directory argument it detects only.
With the directory argument it lazily loads the selected language dictionary:

```json
{"text":"hello world","locale":"en-US","role":"corpus"}
```

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
