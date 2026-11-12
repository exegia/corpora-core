# PDF → TEI → Text-Fabric converter

`pdf-to-tf` turns a local PDF into Text-Fabric (TF), with a score gate in front and
a report at the end:

1. **Extract.** The Rust `corpora-pdf-extract` binary reads text and layout with
   Poppler and Tesseract OCR. It OCRs every page, including pages with a text layer,
   so the text can be checked against the rendered page.
2. **Gate.** It computes a conversion score. Only if the score is **greater than
   95%** does it continue. Otherwise it writes the report and stops.
3. **TEI.** It writes a TEI P5 file: every extracted line, word, page and position.
4. **TF.** It converts that TEI with the existing `tei-to-tf` engine.
5. **Verify.** It reloads the TF with the real loader and checks every line, word and
   page against the extraction.
6. **Report.** It lists every issue with its location and a suggested fix.

## Run

```sh
cargo build -p corpora-pdf --bin corpora-pdf-extract
uv run --project packages/pdf-to-tf pdf-to-tf book.pdf --output target/pdf-to-tf/book \
  --extractor target/debug/corpora-pdf-extract --languages eng+heb
```

Open `target/pdf-to-tf/book/conversion-report.md` first. The output directory must not
exist yet.

| Option | Default | Meaning |
| --- | --- | --- |
| `--output DIR` | required | New bundle directory |
| `--extractor PATH` | `corpora-pdf-extract` on `PATH` | Rust extraction binary |
| `--languages L` | `eng` | Tesseract languages, e.g. `eng+heb`; every one must be installed |
| `--tessdata DIR` | Tesseract default | Directory of `.traineddata` models |
| `--max-pages N` | 200 | Refuse longer PDFs |
| `--min-score X` | `0.95` | Convert only when score > X |
| `--no-visual-check` | off | Skip OCR of text-layer pages; that text then scores 0 |
| `--schema PATH` | none | Validate the TEI against a local self-contained RNG/XSD |

| Exit | Status | Meaning |
| ---: | --- | --- |
| 0 | `converted` | TF written and verified; no warnings or errors |
| 0 | `converted_with_issues` | TF written and verified; the report lists issues to review |
| 3 | `gated` | Score ≤ threshold; report and extraction only, no TEI/TF |
| 1 | `verification_failed` | TF written but differs from the extraction; do not use it |
| 2 | error | Bad input, extractor failure, or output already exists |

Python: `from pdf_to_tf import convert` with the same options as keyword arguments;
it returns the report dictionary.

## The score

```
score = Σ(page_score × page_characters) / Σ(page_characters)
```

`page_characters` counts non-whitespace extracted characters. `page_score` comes
from `corpora-pdf`:

- **OCR pages:** the mean Tesseract word confidence.
- **Text-layer pages:** the token overlap between the text layer and OCR of the
  rendered page.

A page with text but no visual score counts as 0, because nothing confirmed it.
This happens when OCR is unavailable or `--no-visual-check` is set. Blank pages
carry no weight.

**The score is evidence, not accuracy.** It is not measured against a reference
transcription. A confident OCR model can still be wrong. Pointed Hebrew is the
main example: Tesseract drops vowel marks with high confidence, which is why
script-mark findings appear in the report whatever the score. Use the
[held-out benchmark](../../crates/corpora-pdf/benchmarks/PHASE2.md) for accuracy.

When the gate stops a conversion, the report says why for each page. The most
common cause is a language without an installed OCR model, for example a Greek PDF
checked with `--languages eng`.

## Why TEI first

We compared PDF → TF directly with PDF → TEI → TF.

| | Direct PDF → TF | PDF → TEI → TF (chosen) |
| --- | --- | --- |
| Reviewable intermediate | None; TF is not meant for hand editing | A standard TEI file scholars can read, validate and correct |
| Correct, then rerun | Requires a new PDF extraction | Edit the TEI and convert it again with `tei-to-tf` |
| Fidelity checks, source retention, quality loop | Would need rebuilding | Reused from `tei-to-tf` (real loader, exact text, dictionaries) |
| PDF pages and positions in TF | Native | Needed two opt-in `tei-to-tf` options (below) |

The TEI route was worth it once `tei-to-tf` stopped losing PDF structure.
Without them, `pb` page breaks became offsets in a sidecar file and positions
became an opaque string. The two `tei-to-tf` options are off by default, so
other TEI conversions are unchanged:

- `--milestones pages`: each `pb` becomes a TF `page` node, running to the next `pb`.
- `--facsimile zones`: `@facs` resolves to integer `facs_ulx/uly/lrx/lry` features.

pdf-to-tf also runs `tei-to-tf` with its existing `--notes include` option, so
footnote lines stay in the TF text where they are printed and every extracted
line can be verified.

## Feature mapping

| PDF extraction | TEI | Text-Fabric |
| --- | --- | --- |
| Page | `pb@n` + `facsimile/surface` | `page` node: `page`, `facs_surface`, `facs_*` |
| Line / word bounds | `zone` via `@facs` | `facs_ulx`, `facs_uly`, `facs_lrx`, `facs_lry` (int) |
| Heading h1–h4 | `div[@type=section]/head[@type=hN]` | `element`, `tei_tag=head`, `parent` edges |
| Paragraph line | `p[@n]/seg[@type=line]`; `@n` is the paragraph number, repeated when a paragraph continues on the next page | `element`, `tei_tag=seg` (and `p`) |
| List item | `list/item` | `element`, `tei_tag=item` |
| Reference line | `listBibl/bibl[@n]/seg[@type=line]`; one `bibl` per bibliography entry, `@n` repeated when an entry continues on the next page. Extractions without entry numbers get one `bibl` per line | `element`, `tei_tag=seg` (and `bibl`) |
| Citation | `ab[@type=citation]` | `element`, `tei_tag=ab` |
| Footnote line | `note[@place=foot]/seg[@type=line]`, one `note` per note number | `element`, `tei_tag=seg` (and `note`) |
| Running header / footer | `fw[@type=header]` / `fw[@type=footer]` | `element`, `tei_tag=fw` |
| Journal title, title, author, affiliation, publication metadata, abstract, keywords | `ab[@type=journal-title\|title\|author\|...]/seg[@type=line]` | `element`, `tei_tag=seg` (and `ab`) |
| Table cell | `table/row/cell` | `element`, `tei_tag=cell` |
| OCR word + confidence | `w[@cert]` | `element`, `tei_tag=w`, `attr_cert_*` |
| Bold / italic / link | `hi[@rend]` / `ref[@target]` | `element`, `tei_tag=hi` / `ref` |
| Line identity | `@xml:id = p{page}e{index}` | `attr_id_*` |
| Page language (reliable only) | `@xml:lang` (BCP 47) | `attr_lang_*` |
| Image / graph candidate | `figure` (no text) | Not a node: TF nodes need text. Kept in TEI and document JSON |

Slots are Unicode characters, as in `tei-to-tf`. Line text is the engine's output
unchanged. The converter adds only separators: a newline between lines and
blocks, and a tab between table cells. OCR word spaces are already part of the
line text.

Coordinates are integer tenths of Poppler's 108-DPI layout units, with the origin
at the top left of the rendered MediaBox. `extraction.json` keeps the original
floats. `manifest.json` (in `tei-to-tf/`) maps the hashed `attr_*` feature names.

Headings, lists, tables and paragraph grouping are layout guesses from
`corpora-pdf`, not tags stored in the PDF. Paragraphs split at a vertical gap of
0.6 median line heights and always close at a page break.

## The report

`conversion-report.md` is for reading; `conversion-report.json` has every field.

- **Status, score and gate.** For a gated run, the cause for each weak page.
- **A page table.** Method, characters, score and basis.
- **Issues, grouped by code.** Each has a severity, a suggested fix and a
  location: page, line index, word index, bounds, TEI `xml:id` and TF node.
  The Markdown file shows up to 50 rows per code; the JSON file has them all.
- **Verification counts and the feature mapping.**

| Code | Severity | Raised when |
| --- | --- | --- |
| `unscored_page` | error | Page text has no visual check |
| `xml_incompatible_character` | error | A character XML 1.0 cannot store (replaced by U+FFFD) |
| `verification_mismatch` | error | TF differs from the extraction |
| `low_visual_agreement`, `low_ocr_confidence` | warning | Engine page findings under 60% |
| `visual_check_unavailable`, `no_text_found` | warning | OCR missing, or no text found |
| `script_marks_review`, `script_model_unverified` | warning | Marks or scripts that need image review |
| `low_element_score` | warning | Line evidence under 80% |
| `visual_semantics_unverified` | warning | Images or graphs are not transcribed |
| `mark_not_located`, `mark_overlap_dropped`, `words_text_mismatch` | warning | Formatting or words that could not be placed exactly |
| `low_confidence_word` | info | OCR word confidence under 60% |
| `table_structure_heuristic`, `visual_not_in_tf`, `page_scan_image`, `whitespace_element_omitted` | info | Expected losses, recorded |

## Outputs

| Path | Contents |
| --- | --- |
| `conversion-report.md`, `conversion-report.json` | Status, score, issues, mapping, verification |
| `extraction.json` | Full engine output, unchanged |
| `sources/SHA256` | Original PDF bytes |
| `document.tei.xml` | TEI P5 (not written when gated) |
| `tei-to-tf/` | `tf/*.tf`, documents, manifest and checksums from `tei-to-tf` |
| `checksums.json` | SHA-256 of every file in the bundle |

Output is staged and appears only when complete. The original PDF is never modified.

## Limits

- Images and charts are not transcribed. Complex or spanning tables are not rebuilt.
- Reading order follows the engine; multi-column layouts need checking.
- Running headers and footers are not separated from body text.
- Hosted recognition is not run automatically. The suggested fix for weak
  regions is `crates/corpora-pdf/tools/ocr_review.py --provider vercel`, which
  produces review-only candidates.
- TEI schema validation runs only with `--schema`. The TEI is not checked
  against `tei_all` by default.

## Verify

```sh
cargo build -p corpora-pdf --bin corpora-pdf-extract
make -C packages/pdf-to-tf check build
```

The tests use synthetic extractions for the exact mapping rules, a fake extractor
for the command line, and the real binary on the three `corpora-pdf` fixtures
when Poppler and Tesseract are installed (`PDF_EXTRACTOR` overrides the binary
path). `.github/workflows/pdf-converter.yml` runs them on PRs. See
[VERIFICATION.md](VERIFICATION.md) for recorded runs.
