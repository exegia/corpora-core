# EPUB to Text-Fabric (first boundary)

Build the reusable Rust validator, then run the local exporter:

```sh
cargo build -p corpora-convert --bin corpora-epub-check
uv run --project packages/epub-to-tf epub-to-tf book.epub output/bundle \
  --checker target/debug/corpora-epub-check
```

The Rust `corpora_convert::epub::validate_epub(&[u8])` API returns an archive hash,
expanded member hashes, OPF identifier/metadata, a linear spine reading projection,
and shared `corpora-core` diagnostics. The CLI emits this as JSON and exits 1 on
blocking findings. The Python exporter only writes a bundle after validation;
it keeps the original EPUB under `sources/`, per-item JSON and exact main text under
`documents/`, note JSON and exact note text under `notes/`, referenced raster images
under `assets/`, and deterministic `.tf`
files under `tf/`. Its internal Text-Fabric
round trip is verified before publication. Runtime caches are removed from the
bundle.

## Supported policy

- Local ZIP EPUB, one container rootfile, EPUB 2 or 3 OPF, UTF-8 XML, unencrypted
  reflowable XHTML in linear spine order. OPF `unique-identifier` selects the
  publication identity; the filename has no identity role.
- XHTML body text is concatenated in DOM order with no inserted whitespace or
  normalization. Character slots preserve Unicode scalar order. Nonempty XHTML
  elements retain parent, tag, attributes and scalar spans. Publication metadata
  and EPUB3 navigation resources are recorded outside reading text.
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
- Referenced JPEG, PNG, GIF and WebP images in linear XHTML are copied byte-for-byte
  to content-addressed `assets/` files. The manifest and each document's
  `image_assets` TF feature carry the source member, original `src` and `alt`,
  expanded-member byte offset, Unicode scalar text position, media type, hash,
  and asset path. Images occupy no character slots, so adjacent words are never
  separated by invented whitespace. The original archive retains all resources,
  including images not referenced by reading XHTML.
- Non-linear spine items remain unsupported. Missing manifest/spine targets, unsupported media or layout,
  scripted/rich media, responsive images, images inside note bodies, encryption and malformed XML also block. No
  spelling or AI step can clear these structural findings. Fix the source and
  rerun validation; this package does not repair it.
- Maximum 80 MiB original archive, 1024 members, 16 MiB expanded per member, 64 MiB expanded total, and
  one million character slots. Unsafe archive paths, duplicate members and
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
