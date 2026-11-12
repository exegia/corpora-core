# corpora-pdf

`corpora-pdf` is a Rust **library** for local PDFs. Pass it a path and it returns
page text, page positions, semantic candidates, links and formatting, language
hints, visual elements, findings, and an evidence-based extraction score. It
does not export Text-Fabric or provide a web API. The `corpora-pdf-extract`
binary prints one `PdfExtraction` as JSON; [`pdf-to-tf`](../../packages/pdf-to-tf/README.md)
uses it to convert PDFs to TEI and Text-Fabric.

```sh
cargo build -p corpora-pdf --bin corpora-pdf-extract
target/debug/corpora-pdf-extract book.pdf --languages eng+heb [--tessdata DIR] \
  [--max-pages N] [--no-visual-check] > extraction.json
```

It exits 2, with the error on stderr, for invalid arguments or a failed extraction.

The crate includes the [pdf-ocr skill](skills/pdf-ocr/SKILL.md), its
[specialist prompt](agent/SYSTEM.md), and the [implementation proposal](agent/PROPOSAL.md).
These distinguish possible mark loss from an exact image-verified discrepancy
and define optional paid recognition without overwriting source extraction.

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

On text-layer pages, Poppler starts a new text fragment at every font change, so
one printed line can arrive in pieces (a small-caps heading, an italic word, a
footnote number). Fragments that share most of their height and are no further
apart than a word space (0.8 line heights) are joined into one line element, in
either order, so the line keeps its text, marks and a single bounding box. Page
columns and table columns sit further apart and stay separate. Text that the PDF
draws twice at the same place (an overprint) is kept once, as `pdftotext` does.
A text-layer table needs rows of two or more non-blank cells, at least one of
them no wider than four line heights, with neighboring rows that start their
cells at the same places; two prose columns that share baselines are not a table.
These layout rules remain heuristic: they do not establish correct reading order
for every PDF, reconstruct complex tables, or repair an OCR model's script errors.

Once every page is extracted, a document pass adds labels that need more than one
line. Blank lines are dropped after it runs.

- `running_header` / `running_footer`: a line in the top or bottom 10% of the
  page whose letters repeat in that band on another page, or a bare page number.
  It must be the page's outermost text: a line with a title above it is body
  text. A page number at the foot needs space above it, so a wrapped note line
  such as "243." stays a footnote; a standalone page number below the footnote
  rule is still a `running_footer`. A heading set larger than 1.15 times the body
  text is never page furniture; a running head set in bold capitals at body size
  is. A linked source notice set apart at the foot of a page (for example a
  repository notice on a cover page) is also a `running_footer`.
- `footnote`: every line below the footnote rule (a long blank, underlined run in
  the lower half of the page). Without a rule, a run of smaller lines at the foot
  of the page that starts with a note number followed by note text.
- Section labels such as "Abstract", "Keywords", "Recommended Citation" and
  "Cover Page Footnote" become `h2` headings, and the lines right under them
  become `abstract`, `keywords`, `citation` or `footnote`. A centred line in
  capitals ("INTRODUCTION") or a centred section number ("2.", "IV") is an `h2`
  when body text with lowercase letters follows within five line heights, so a
  cover page set in capitals and table cells in scripts without case stay body
  text. Every line under "Bibliography", "References" or "Works Cited" is a
  `reference` until the next heading of the same or a higher level, across pages;
  subheadings such as "Primary" and "Secondary" do not end it.
- Front matter, only on the first two pages, before any running header, and only
  when a page shows issue details ("Volume 1", "October 2010") or an abstract,
  keywords or citation label: large lines above the issue details are the
  `journal_title`, large lines below them the `title`; the name line after the
  title is the `author`, followed by `affiliation` lines; issue details are
  `publication_metadata`.
- `paragraph` lines carry a `paragraph` number, counted through the document, so
  the lines of one visual paragraph share it. A paragraph starts at a line
  indented past the line above it, after a gap larger than the page's usual line
  spacing plus a third of a line (at least half and at most 0.6 of a line, so
  uneven spacing on a scan stays one paragraph and double-spaced table rows stay
  apart), or after anything that is not body text (a heading, list, image). A
  full-width last line at the foot of one column continues at the top of the next
  column when that line is not indented and only page furniture lies between them
  in Poppler's order. Lines are linked
  by position, not by Poppler's output order, and each paragraph's lines are put
  together, top to bottom, where its first line was extracted: Poppler can emit
  the end of a paragraph after the next paragraph's lines. Pages where two
  paragraph lines share a row (page columns, or a printed line Poppler left in
  pieces) keep Poppler's order. A paragraph keeps its number on the
  next page when the page's last body line is full width and the next page's first
  body line is not indented.
- A numbered list item needs a space and text after its marker, so a DOI
  ("10.70623/NAJW4433.") or a continued page number ("243.") is not a list item.
  A citation needs a bracketed number (`[1]`, `[2, 5]`), not any bracketed word.

### What the labels and score mean

- On text-layer pages, `h1`–`h4` use relative font size plus bold evidence.
  On OCR pages, heading candidates use line height and short-line cues.
  `section_path` records heading ancestry. List, citation, reference, table-cell,
  page furniture, footnote and front-matter labels use layout/text cues. They are candidates to review, not guaranteed source tags.
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
original page rendered to PNG at 108 DPI (the extraction coordinate scale), with
a link to the unchanged PDF. This works without an embedded PDF plugin.
The middle pane shows element types, text, positions, marks,
scores, and findings. Findings start collapsed; script findings link to their
numbered extracted element. The generic viewer in `tests/browser/` consumes
`review.json` units; the PDF builder is a format adapter and also retains the
raw engine `result.json`. Existing TEI and EPUB QA generators keep their
current output contracts.

A third column, "TEI rendering", shows the page as `pdf-to-tf` would encode it.
The builder runs `pdf-to-tf`'s TEI builder (`uv run --project packages/pdf-to-tf`)
on `result.json`, writes `document.tei.xml`, and the page renders it as HTML:
section headings, numbered paragraphs, footnotes, running headers and footers,
front-matter blocks, bibliography and tables, each labelled with its type ("Show
types" hides the labels). Lines keep their `p{page}e{index}` ids, so the column
shows only the current page and clicking a line jumps to its element card. Pass
`--no-tei` to build without it. Script and style URLs carry a content hash, so a
reload after a rebuild never runs a cached copy.

```sh
python3 tests/browser/build_pdf_review.py path/to/book.pdf /tmp/pdf-review --languages eng
python3 -m http.server 8771 --bind 127.0.0.1 -d /tmp/pdf-review
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

## Script review and specialist candidates

Extraction emits additive `script_review` findings with page/region coordinates,
script, observed marks and a pinned raw-text revision. Missing accents are unknown
until verified against source evidence; ordinary unpointed Hebrew is not an error.
See [the region tool guide](tools/README.md) for bounded local Kraken and optional
Vercel AI Gateway or direct Mistral requests, private caching and mark-aware reference comparison.
