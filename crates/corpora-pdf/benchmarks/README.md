# PDF accuracy benchmark

Run from the repository root. This test-only Python runner invokes the Rust
engine on source-pinned pages and on lossless raster copies without text layers.
It does not modify the source, repair OCR, call hosted AI, or export TF.
Poppler, Tesseract and Cargo must be installed; Python uses only the standard library.

```sh
python3 -m unittest discover -s crates/corpora-pdf/benchmarks -p 'test_*.py'
python3 crates/corpora-pdf/benchmarks/benchmark.py \
  crates/corpora-pdf/benchmarks/fixture.json target/pdf-fixture-benchmark
```

The output directory must be new. It contains `report.json`, an offline dark
`index.html`, source page images, selected page PDFs, raster PDFs and both raw
engine responses. Open `index.html` directly; this report requires no HTTP server
or JavaScript fetch. Keep real books, references and reports under ignored
`target/` or another private directory. The report contains local source paths
and selected source text; it is not intended for public publishing.

## Add a real sample

Copy the fixture manifest to a private `manifest.local.json`. Each sample has a
unique safe `id`, a `path` (absolute or relative to the manifest), the original
PDF's `sha256`, a one-based physical PDF `page`, and `regions`. Hashes are checked
before extraction. Logical printed page labels are not PDF page numbers.

Each region records `id`, `box: [left, top, right, bottom]` in normalized page
coordinates, `reference` transcribed from the visible image, and
`reference_status`: `visual_transcription_unreviewed` or `human_verified`.
Synthetic fixtures use `independently_specified_fixture` for builder-defined text.
Do not derive a reference from the hidden PDF text or the OCR being tested.
Inspect enlarged images for vowel marks, Greek accents, footnote markers and
punctuation; unresolved readings must remain unreviewed. Use small, whole-line
or whole-cell regions. Optional `order: [["first", "second"]]` checks that all
selected elements in one region precede the other in the engine result.

```sh
python3 crates/corpora-pdf/benchmarks/benchmark.py \
  target/pdf-benchmark/manifest.local.json target/pdf-benchmark/new-run --languages eng
```

The default is the installed English OCR model. `--languages eng+heb` requires
those models already installed. A missing model fails the run; the runner never
downloads models. Preserve baseline language settings when comparing runs.

Use `--tessdata-dir /path/to/models --languages eng+heb` to select an isolated
model set without changing the machine-wide installation. The report records
the actual model directory and SHA-256 of each requested model. It rejects a
missing requested language before extraction; the Rust bridge also rejects
Tesseract's partial-success response when one listed model cannot load.
Compare English-only and English-plus-Hebrew using the same English model file
to separate language-selection effects from model-family changes.
Compare CER only over regions that are spatially bounded in every compared run;
report that common coverage explicitly. A lower score on fewer regions is not
evidence of an improvement on the whole sample.

## What the measurements mean

- **CER/WER:** Levenshtein character/word edit counts divided by reference length.
  Lower is better; insertions can exceed 100%. Normalize NFC and collapse
  whitespace, retaining case, punctuation, vowel marks and printed hyphenation.
  Missing text counts as deletions. Element boundaries are joined with one space;
  spacing introduced by segmentation therefore remains visible in the metric.
- **Region alignment:** select text by element center without reordering it.
  Any text element crossing a region boundary makes that region ambiguous;
  exclude its text score from the aggregate and show the alignment failure.
  This prevents merged OCR table rows from masquerading as measured cell accuracy.
- **Reading order:** independent of CER/WER. Correct words can still be interleaved
  between columns. A missing region fails an order check.
- **Engine score:** display the original page confidence/agreement separately.
  It is neither a reference accuracy score nor calibrated by this small sample.
- **Coverage:** measure only declared regions; never extrapolate to a page or book.
  Reports retain reference-review status, engine revision and binary hash, working
  tree state, manifest and benchmark hashes, OCR version and installed languages.

## Initial attached-document pilot

The November 9 pilot uses four pages from the user's eight attachments:
Aramaic grammar PDF page 25 (comparison table), Hebrew syntax PDF page 40
(bibliographic references), Athanasius PDF page 20 (historical scan), and Aune
PDF page 3 (two-page spread). The other four attachments were inventoried but
have not been benchmarked. References were transcribed visually by the assistant
and are explicitly awaiting human verification. No full-book acceptance is claimed.

The first pass exposed Hebrew vowel loss/direction problems in the source text
layer, merged table cells in English-only OCR, and a reading-order inversion on
the rasterized Aune spread. These failures occurred alongside high page-level
confidence/agreement. A follow-up preserves OCR word geometry, separates repeated
aligned table cells and retains Tesseract's column block order. All three table
regions become spatially bounded and Aune's reading-order check passes; Hebrew
recognition errors remain. See [the verification record](VERIFICATION.md).
Before tuning thresholds, expand reference coverage and installed OCR languages.

The subsequent pinned `tessdata_best` comparison (`eng`, `eng+heb`, `heb+eng`)
recovers sampled Hebrew consonants but misses vowel marks and changes table
grouping. The Hebrew model's output alphabet lacks the required holam mark.
This is a failed pointed-text acceptance result, not a default-model upgrade;
see the verification record for exact hashes, coverage and local evidence paths.
