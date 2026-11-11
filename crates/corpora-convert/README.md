# corpora-convert: check an EPUB before exporting it

An EPUB is a ZIP full of files. This Rust crate opens the ZIP **in memory**,
finds the book's reading order, and reports what it found. Think of the result
as a checked map of the book. It does not write Text-Fabric files; the
[EPUB Python package](../../packages/epub-to-tf/README.md) uses this map to do that.

## Rust API

Add `corpora-convert` as a dependency, then pass the **original EPUB bytes**:

```rust
use corpora_convert::epub::validate_epub;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let epub = std::fs::read("book.epub")?;
    let report = validate_epub(&epub);
    if !report.passed() {
        for finding in &report.findings {
            eprintln!("{}: {:?}", finding.member, finding.report.diagnostics);
        }
    }
    println!("publication ID: {:?}", report.identifier);
    println!("reading documents: {}", report.documents.len());
    Ok(())
}
```

| Entry point | Input | Purpose |
| --- | --- | --- |
| `validate_epub(bytes)` | Complete `&[u8]` archive | Check with the default limit of 1,000,000 Unicode character slots. |
| `validate_epub_with_slot_limit(bytes, max_slots)` | Archive bytes and requested slot count | Check a large book; the hard ceiling is 8,000,000 slots. |
| `EpubReport::passed()` | No parameters | `true` only when no finding blocks export and at least one reading document exists. |

`EpubReport` keeps `archive_sha256`, expanded-member `members` with their hashes,
the OPF `identifier`, publication `metadata`, excluded `navigation`, spine-order
`documents`, separate `notes`, `note_references`, `images`, all `assets`, and
member-scoped `findings`. Each reading document has its manifest ID, archive
member, exact decoded text, and XHTML elements with parent keys and half-open
Unicode scalar spans. Notes have their own text; note markers link to them.
Assets have source positions and checked manifest targets. `images` is the
image-only subset of `assets` for existing callers.

Findings use the [shared diagnostic contract](../corpora-core/README.md#shared-structural-and-spelling-diagnostics).
Coordinates identify an **expanded member's UTF-8 bytes**, with decoded scalar
positions where available. They are never compressed ZIP offsets. An archive
failure with no known member has no invented line number.

## JSON command

From the repository root:

```sh
cargo run -p corpora-convert --bin corpora-epub-check -- book.epub > report.json
cargo run -p corpora-convert --bin corpora-epub-check -- book.epub --max-slots 8000000 > large-report.json
```

The command prints the report as JSON. Exit code `0` means validation passed,
`1` means a checked EPUB has blocking findings, and `2` means command/input
failure. `--max-slots N` has the same hard ceiling as the Rust API. Feed a
passing report to the Python exporter rather than extracting ZIP members yourself.

## What this checker accepts

It follows `META-INF/container.xml` to one OPF package, reads its metadata,
manifest and linear spine, then projects unencrypted, reflowable XHTML in spine
order. OPF's `unique-identifier` chooses the book ID; the filename does not.
Navigation and publication metadata stay outside reading text. XHTML text is
kept in DOM order without invented spaces. Recognized note bodies are separate
from the main stream and connected to their markers. Supported image and media
references are retained as asset records.

It blocks unsafe archive paths, duplicate members, missing targets, encryption,
unsupported layout/content, and structures it cannot convert faithfully.
Bounds are 80 MiB archive bytes, 1,024 members, 16 MiB expanded per member,
64 MiB expanded total, and 1,000,000 slots by default. XML entity/network
loading is disabled. See the [export policy](../../packages/epub-to-tf/README.md#supported-policy)
for the detailed EPUB and repair boundaries. This is a bounded converter input
check, not a full EPUB conformance test.

## Check this crate

```sh
cargo test --locked -p corpora-convert
cargo clippy --locked -p corpora-convert --all-targets -- -D warnings
```

License: MIT OR Apache-2.0.
