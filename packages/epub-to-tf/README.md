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
it keeps the original EPUB under `sources/`, per-item JSON and exact text under
`documents/`, and deterministic `.tf` files under `tf/`. Its internal Text-Fabric
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
- Non-linear spine items and notes block conversion until a separate reading
  policy is chosen. Missing manifest/spine targets, unsupported media or layout,
  embedded images/scripts/media, encryption and malformed XML also block. No
  spelling or AI step can clear these structural findings. Fix the source and
  rerun validation; this package does not repair it.
- Maximum 80 MiB original archive, 1024 members, 16 MiB expanded per member, 64 MiB expanded total, and
  one million character slots. Unsafe archive paths, duplicate members and
  ZIP extraction to disk are forbidden. DTDs are rejected; the XML parser does
  not fetch network resources or external entities.

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
