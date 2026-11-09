# EPUB to Text-Fabric (first boundary)

Build the reusable Rust validator, then run the local exporter:

```sh
cargo build -p corpora-convert --bin corpora-epub-check
uv run --project packages/epub-to-tf epub-to-tf book.epub output/bundle \
  --checker target/debug/corpora-epub-check
```

For a large book with repairable malformed XHTML, opt into the audited repair
phase and an explicit larger character bound:

```sh
uv run --project packages/epub-to-tf epub-to-tf book.epub output/repaired-bundle \
  --checker target/debug/corpora-epub-check --repair --max-slots 8000000
```

The Rust `corpora_convert::epub::validate_epub(&[u8])` API returns an archive hash,
expanded member hashes, OPF identifier/metadata, a linear spine reading projection,
and shared `corpora-core` diagnostics. The CLI emits this as JSON and exits 1 on
blocking findings. The Python exporter only writes a bundle after validation;
it keeps the original EPUB under `sources/`, per-item JSON and exact main text under
`documents/`, note JSON and exact note text under `notes/`, referenced assets
under `tf/assets/`, and deterministic `.tf` files under `tf/`. Its internal Text-Fabric
round trip is verified before publication. Runtime caches are removed from the
bundle.
Bundle format `corpora-epub-to-tf/2` keeps exact source text in each `.txt`,
`text.tf`, and `sources/original.epub`. Each `.reading.txt` and the default
`T.text()` format use the display projection described below. The explicit
`T.text(node, fmt="text-source-full")` format returns the exact source string.
With `--repair`, it keeps `sources/original.epub`, writes the separate
`sources/repaired.epub`, `sources/repair-ledger.json`, and initial/final Rust
diagnostics, then requires the repaired archive to pass the same validator.
The manifest distinguishes original `source` from `validated_source` hashes.

## Supported policy

- Local ZIP EPUB, one container rootfile, EPUB 2 or 3 OPF, UTF-8 XML, unencrypted
  reflowable XHTML in linear spine order. OPF `unique-identifier` selects the
  publication identity; the filename has no identity role.
- XHTML body text is concatenated in DOM order with no inserted whitespace or
  normalization in the source projection. Character slots preserve Unicode scalar
  order. Nonempty XHTML elements retain parent, tag, attributes, member byte
  coordinate, source scalar spans, and reading-view spans. Publication metadata
  and EPUB navigation resources are recorded outside reading text.
- The default reading view reduces each run of horizontal layout whitespace to
  one ASCII space, or each run containing a linebreak to one `\n`. Leading and
  trailing layout runs disappear. U+200B zero-width spaces and U+FEFF layout
  marks disappear from this view; joiners and non-joiners remain. `pre`, `code`,
  `textarea`, and `xml:space="preserve"` spans retain exact whitespace. This
  policy never inserts separators absent from the source. The original slots
  and exact text stay available for audit; asset and element records retain both
  source and reading offsets.
- Explicit XHTML headings become `semantic_kind=heading` with `heading_level`;
  declared subtitles become `subtitle`. Marked verse numbers become
  `verse_number`. Links carry `link_kind` (`navigation`, `reference`, or `note`),
  original `link_href`, resolved local member/fragment where possible, and
  source byte location. Navigation classification requires a `nav`, TOC, or
  chapter-menu context; ordinary prose links remain references. The converter
  does not infer verse numbers from bare digits or guess that every internal
  link is navigation.
- EPUB3 TOC navigation is parsed into ordered, nested `manifest.json` `toc`
  entries with label, target member, fragment, parent, level, and source line.
  NCX is the fallback. Missing/external TOC targets block export. Each target
  document also has a `toc_entries` TF feature; links in a reading TOC page
  remain marked as navigation links.
- Every reading XHTML element, including zero-length `br` and `img`, has an
  `element` node with `xhtml_tag`, source attributes, parent edge, source
  byte location, and raw/reading spans. A zero-length element has
  `empty_element=1` and is anchored to an adjacent character slot only because
  Text-Fabric nodes require slots; its `start=end` and `reading_start=reading_end`
  are the authoritative positions. Do not use `T.text(empty_element_node)` as
  the element's content.
- `tools/qa_browser.py` loads the `.tf` features and emits a sandboxed semantic
  reading page for each spine item. It retains headings, lists, tables, links,
  inline markup, referenced notes, empty elements, and copied image paths. The page uses the
  normalized TF reading text and a neutral stylesheet; original CSS, head
  metadata, and EPUB reader behavior remain in the archived XHTML view. It is
  a reading-structure reconstruction, not a byte-identical XHTML round trip.
  Inline SVG and MathML are retained as assets but are not embedded into this
  semantic page yet; unfamiliar tags are displayed as spans with their source
  tag name in `data-source-tag`.
- Referenced EPUB `footnote` and `endnote` bodies in linear spine XHTML use
  separate character slots and `note` nodes. Markers remain in main text as
  XHTML `element` nodes. A `noteref` edge points from each marker to its note.
  `T.text(document)` therefore excludes note bodies; `T.text(note)` retrieves
  them. Same-member and cross-member links between linear spine resources are
  supported, including multiple markers for one note.
- Note bodies require a unique fragment ID and nonempty text. Markers require
  nonempty text and a resolvable local `href`; orphan notes, duplicate IDs,
  nested notes or note references, and percent-encoded fragments block export.
  Each note has a stable `member#fragment` source key. Marker records retain
  their original `href`, label, member and raw member-byte offset. These keys
  can later be mapped to database rows without relying on TF node numbers.
- Referenced `image/*`, `audio/*`, and `video/*` manifest resources, captions
  (`text/vtt` or TTML), embedded PDFs, inline passive SVG and inline MathML
  are copied byte-for-byte to content-addressed `tf/assets/` files. Supported
  references come from `img`, `audio`, `video`, `source`, `track`, `object` and
  `embed` elements. Video posters are image references. Each document or note
  node has an `asset_refs` TF feature containing JSON records with kind, MIME
  type, source member, raw expanded-member byte offset, Unicode scalar text
  offset within that document or note, hash, and `tf_path` relative to `tf/`.
  Inline XML assets also retain their exclusive source byte end. The manifest
  keeps the same records with bundle-relative `file` paths. The existing
  document `image_assets` feature remains for image-only queries.
- Assets occupy no character slots; inline SVG and MathML content is preserved
  in the exact XML asset, not added to `T.text()`. Fallback XHTML text in audio,
  video and object elements remains in the reading string. The original archive
  retains all resources, including those not referenced by reading XHTML.
  Opaque media bytes are preserved, but this converter does not decode them or
  guarantee playback in a particular reader.
- Non-linear spine items remain unsupported. Missing manifest/spine targets,
  unsupported media or layout, scripts/iframes, responsive `srcset`, active or
  externally linked SVG, and encryption block export. Malformed XHTML blocks
  by default. With `--repair`, the API may create a strict XHTML candidate
  using a network-disabled HTML recovery parser. It compares decoded body
  text, explicit start tags and attributes against an independent lexical
  parse, records parser findings and member hashes, and runs final Rust
  validation. Misnested source tags have no unique original hierarchy; the
  resulting tree is the documented recovery interpretation. Unexpected
  elements, lost text/tags/attributes and unsupported blockers still fail.
  Spelling or AI never clears structural findings.
- Duplicate XHTML fragment IDs stay blocking by default. With `--repair`,
  later duplicate IDs receive deterministic suffixes only if no local XHTML
  reference targets that ambiguous fragment. Each edit is in the ledger.
  An inbound reference requires manual source correction.
- Maximum 80 MiB original archive, 1024 members, 16 MiB expanded per member, 64 MiB expanded total, and
  one million character slots by default; `--max-slots` can explicitly raise
  this to at most eight million. Unsafe archive paths, duplicate members and
  ZIP extraction to disk are forbidden. Plain HTML and the exact XHTML 1.1
  external doctype are accepted in XHTML members. Internal DTD subsets and other
  doctypes are rejected; the XML parser does not fetch network resources or
  external entities. Named entities absent from the XML source therefore fail.

Diagnostic locations refer to expanded UTF-8 member bytes and Unicode scalars,
not compressed ZIP offsets. Archive-level failures have no invented source
coordinate. This is a bounded reading conversion, not full EPUB conformance or
remote acquisition. Empty elements and non-reading head content remain in the
original archive but have no TF slots.

Run the package checks from its directory:

```sh
cargo build -p corpora-convert --bin corpora-epub-check
uv run --group dev ruff check .
uv run --group dev ruff format --check .
uv run --group dev mypy src
uv run --group dev pytest -q
uv build
```

## Local browser comparison

Generate a dark-mode QA page from any exported bundle, then serve it locally:

```sh
uv run --project packages/epub-to-tf python packages/epub-to-tf/tools/qa_browser.py \
  output/bundle target/epub-qa
python3 -m http.server 8769 --directory target/epub-qa
```

Open `http://127.0.0.1:8769/index.html`. The validated XHTML is shown in a
sandboxed iframe with its EPUB styling, with a toggle to the original archive
member when a repair was needed. The normalized TF reading text, TOC, semantic
marker counts, and asset inventory use dark mode. The text status independently
parses each validated XHTML body and checks both source and reading views using
the documented note and inline-asset exclusion policy. This page is
a visual QA aid; the package tests and actual TF/Context-Fabric loads remain the
conversion acceptance checks.
