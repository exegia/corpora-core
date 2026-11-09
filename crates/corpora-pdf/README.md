# corpora-pdf

`corpora-pdf` is a Rust **library** for local PDFs. Pass it a path and it returns
page text, page positions, semantic candidates, links and formatting, language
hints, visual elements, findings, and an evidence-based extraction score. It
does not export Text-Fabric or provide a production CLI or web API. Another
crate can consume its `PdfExtraction` value for those jobs.

## Install the local engines

This first backend runs [Poppler](https://poppler.freedesktop.org/) for PDF
parsing and page rendering, and [Tesseract](https://tesseract-ocr.github.io/)
for OCR. Both programs must be on `PATH`:

```sh
brew install poppler tesseract
pdftohtml -v
pdftoppm -v
pdfinfo -v
tesseract --version
tesseract --list-langs
```

On other systems, install the equivalent packages. Tesseract's installed
language data controls which scanned languages can be read. Set
`ocr_languages` to codes available in `tesseract --list-langs` (for example
`eng+fra`). Language **identification** is separate: the crate runs `whatlang`
on the extracted page text and sets `language_reliable` to `false` when the
evidence is weak.

## Call the engine

Add `corpora-pdf` as a path dependency from a consuming Rust crate:

```toml
[dependencies]
corpora-pdf = { path = "../corpora-pdf" }
```

```rust
use corpora_pdf::{ExtractOptions, ExtractionMethod, extract_pdf};

fn inspect(path: &std::path::Path) -> Result<(), corpora_pdf::PdfError> {
    let options = ExtractOptions {
        ocr_languages: "eng+fra".to_owned(),
        ..ExtractOptions::default()
    };
    let document = extract_pdf(path, &options)?;
    println!("source sha256: {}", document.source_sha256);
    for page in &document.pages {
        println!("page {}: {:?}, language {:?}", page.number, page.method, page.language);
        for element in &page.elements {
            println!("{:?} at ({:.0}, {:.0}): {}", element.kind,
                element.bounds.x, element.bounds.y, element.text);
        }
        if page.method == ExtractionMethod::Ocr {
            println!("OCR score: {:?}", page.extraction_score);
        }
    }
    Ok(())
}
```

### Options

| Parameter | Default | Purpose |
| --- | ---: | --- |
| `max_pdf_bytes` | 100 MiB | Reject larger input before external processing. |
| `max_pages` | 200 | Reject larger documents. |
| `max_elements_per_page` | 20,000 | Bound text/image and OCR element output. |
| `ocr_max_edge_px` | 2,400 | Longest rasterized page edge sent to OCR. |
| `ocr_languages` | `eng` | Installed Tesseract language codes. |
| `tessdata_dir` | `None` | Optional directory of `.traineddata` models; otherwise Tesseract uses its environment/default lookup. |
| `verify_text_layer_with_ocr` | `true` | OCR rendered pages to compare visible text with PDF text objects. |

`PdfExtraction.pages` are source ordered. `Page.elements` contain `kind`,
`text`, a page-local `bounds` rectangle, inline `marks`, `section_path`,
optional `table_id`, and an optional score. A PDF may have no text layer; then
the page uses OCR text. Images remain visual elements and are **not** treated
as successfully transcribed merely because surrounding text was read.

OCR elements also retain `words`: each word's exact recognized text, rectangle,
and confidence. The field is omitted for text-layer elements and defaults to an
empty list when reading older JSON. Rust callers constructing `Element` directly
must now supply `words` (usually `Vec::new()` for native text).

OCR text keeps Tesseract's block/paragraph/line reading order. The engine does not
globally sort lines by vertical position, which would interleave columns.
Within a block, repeated aligned wide gaps in neighboring rows can separate
short table cells; a single wide space is insufficient. Word order within cells,
including right-to-left recognition order and combining marks, is preserved.
Section ancestry is assigned after grouping in the final reading order.
These layout rules remain heuristic: they do not establish correct reading order
for every PDF, reconstruct complex tables, or repair an OCR model's script errors.

### What the labels and score mean

- On text-layer pages, `h1`–`h4` use relative font size plus bold evidence.
  On OCR pages, heading candidates use line height and short-line cues.
  `section_path` records heading ancestry. List, citation, reference, and table-cell labels use
  layout/text cues. They are candidates to review, not guaranteed source tags.
- `bold`, `italic`, and `link` marks come from Poppler's XML output. Link
  targets remain attached to the marked text. A table is exposed through cells
  with a shared `table_id`; complex spanning tables are not reconstructed.
- Images get `image`. A nearby figure/graph/chart caption can make a
  `graph_candidate`; graph data itself is not extracted. The
  `visual_semantics_unverified` finding flags pages needing visual review.
- For OCR pages, `extraction_score` is mean Tesseract word confidence. For
  text-layer pages, it is token overlap with OCR of the rendered page. Each
  score says which basis it uses. **Neither is measured accuracy against a
  reference transcription.** Low scores add findings; `None` means no visual
  evidence was available. Poor scans can still yield confident errors.

Original PDF bytes are never rewritten. `source_sha256` identifies the input;
page and rectangle identify extracted evidence. Poppler runs on a private PDF
copy because its image extraction can create side files. Encrypted PDFs and
invalid/over-limit inputs fail explicitly. There is no remote acquisition,
handwriting recognition, guaranteed reading order, chart transcription,
complex table reconstruction, or full PDF/UA conformance in this increment.

For multilingual OCR, request all needed models explicitly, for example
`ocr_languages: "eng+heb".to_owned()` with `tessdata_dir: Some(model_path)`.
Every requested language must be listed by Tesseract. Missing or unloadable
models prevent OCR instead of silently falling back to English. On scanned
pages this is an extraction error; on native text pages it leaves the source
text intact and reports `visual_check_unavailable` without a visual score.
Disabling native-page visual verification still avoids OCR entirely.
Model directories need only the language files; the engine enables TSV output
directly without relying on a `configs/tsv` file. Models are never downloaded
by the engine. Adding Hebrew does not establish accurate biblical vowel marks
or Aramaic recognition; measure those against image-based references.

## Review a PDF in the browser

The test-only builder writes a dark, side-by-side site. The left pane shows the
original PDF page. The right pane shows element types, text, positions, marks,
scores, and findings. The generic viewer in `tests/browser/` consumes
`review.json` units; the PDF builder is a format adapter and also retains the
raw engine `result.json`. Existing TEI and EPUB QA generators keep their
current output contracts.

```sh
python3 tests/browser/build_pdf_review.py path/to/book.pdf /tmp/pdf-review --languages eng
python3 -m http.server 8771 -d /tmp/pdf-review
# Open http://127.0.0.1:8771/index.html
```

Use a local loopback server because browsers normally block `fetch` of
`result.json` from a `file://` page. The site copies the source PDF into the
review directory; keep that directory private for sensitive documents.

## Verify

For reference-based character/word error rates and reading-order checks, use the
[region benchmark](benchmarks/README.md). It compares native extraction with
OCR of rasterized pages and keeps alignment failures separate from text accuracy.
Real PDFs and their reports stay outside Git; the checked-in example uses the
synthetic fixture.

The fixtures have independently specified visible wording: one PDF has a text
layer, heading styles, lists, link and table-like rows; the second is an
image-only raster of that page. Rebuild them with the fixture script if needed.

```sh
python3 crates/corpora-pdf/tests/fixtures/build_fixtures.py
cargo test -p corpora-pdf
python3 -m unittest discover -s tests/browser -p 'test_*.py'
make fmt
make ci
```

## Why not PDFluent in this first backend?

We evaluated [PDFluent 1.3.0](https://pdfluent.com/blog/sdk-1-3-0/).
Its integrated layout/table/OCR path is promising, but its structured
extraction API is [Preview](https://pdfluent.com/how-to/extraction/) and its
SDK uses [AGPLv3 or a paid commercial license](https://pdfluent.com/license/).
This crate keeps its public result independent of a backend so that a future
licensing decision and comparative tests can change the engine without changing
consumer data types. Poppler and Tesseract are mature local tools and expose
the page positions, formatting, links, rendered pages, and OCR confidences
needed for this bounded engine.

PDFluent publishes [vendor benchmarks](https://pdfluent.com/benchmarks/) for
structured extraction and speed, but those figures are not an independent
head-to-head test against this engine. This implementation deliberately renders
and OCRs every page by default to provide a visual comparison score, so its
throughput depends heavily on page size and OCR language data. For text-layer
work where a visual score is unnecessary, set `verify_text_layer_with_ocr` to
`false` to skip that extra pass. A representative corpus benchmark is still
needed before choosing a faster production backend.
