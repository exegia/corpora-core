# pdf-to-tf verification

## 2026-11-11: first implementation

Environment: macOS, Poppler `pdftohtml` 26.11.0, Tesseract 5.5.4 (`eng` only),
rustc 1.99.1, Python 3.13 via uv, text-fabric 13.1.2 (pinned).

```sh
cargo build -p corpora-pdf --bin corpora-pdf-extract
cargo clippy --workspace --all-targets --all-features -- -D warnings
cargo test -p corpora-pdf
make -C packages/tei-to-tf check        # 146 passed, 11 skipped
make -C packages/pdf-to-tf check build  # 22 passed, wheel and sdist built
```

### Crate fixtures through the real extractor

| Fixture (sha256 prefix) | Pages | Status | Score | Lines / words / pages verified | Issues |
| --- | ---: | --- | ---: | --- | --- |
| `semantic.pdf` (`adedbfb3a59071b1`) | 1 text layer | converted | 100.00% | 11 / 0 / 1 | 1 info (table rows inferred) |
| `mixed.pdf` (`ce97fedaa9dfc814`) | 1 text layer + 1 scan | converted | 98.21% | 22 / 24 / 2 | 3 info (2 tables, page-scan image) |
| `scanned.pdf` (`8a55b2d761ae3887`) | 1 scan | converted | 96.43% | 11 / 24 / 1 | 2 info (table, page-scan image) |

Verification found 0 mismatches. It checked:

- every line's text and TEI tag;
- every line's zone coordinates and page membership;
- every OCR word's text, zone and confidence.

The installed `text-fabric-validator` reported no errors on the `mixed.pdf` TF. It
gave one TF064 warning and one TF065 notice, which `tei-to-tf` documents as
expected for character slots.

### Real document, gate stops it

`69-SBLGNT-Galatians.pdf` is 8 text-layer pages of Greek. The PDF is private and
was not committed.

| Run | Status | Score | Why |
| --- | --- | ---: | --- |
| `--languages eng+grc+ell` | gated | 0.00% | `grc`/`ell` models not installed, so OCR failed. All 8 pages unscored (8 `unscored_page` errors) |
| `--languages eng` | gated | 18.61% | English OCR cannot confirm Greek text (13–22% agreement per page). The report names the detected `ell` and says to add it |

Both runs wrote only the report, `extraction.json` and the source copy. No TEI or
TF was written. Both stopped for the right reason: the text could not be
checked, not because it was shown to be wrong. A converted run on this PDF
needs a Greek Tesseract model. GitHub, which hosts the models, was unreachable
from this machine during the run.

### Not established

- Accuracy against reference transcriptions. The score is evidence; see the
  README.
- Multi-column reading order, running headers and footers, and complex tables
  on real books.
- Behavior on the long Hebrew and Aramaic PDFs: they exceed the default 200-page
  limit, and Hebrew/Aramaic accuracy is measured separately in the
  [held-out benchmark](../../crates/corpora-pdf/benchmarks/PHASE2.md).

## 2026-11-12: line fragments and false tables

QA of `corpora-web/samples/triadic-to-trinitarian.pdf` (15 text-layer pages, English)
showed small-caps headings split into one element per font run, and ordinary prose
labelled as table cells. Cause: `corpora-pdf` kept every Poppler fragment as its own
element, and treated any two rows of two or more fragments as a table. The fix joins
same-line fragments, keeps overprinted text once, ignores blank fragments as cells,
and applies the OCR path's short-cell and alignment rules to text-layer tables.

| Article run | Before | After |
| --- | ---: | ---: |
| Score | 96.80% | 98.68% |
| Table cells | 374 | 0 |
| `low_element_score` warnings | 104 | 28 |
| `table_structure_heuristic` notes | 179 | 0 |
| Verification mismatches | 0 | 0 |

The 28 remaining warnings are footnote lines whose superscript numbers OCR reads
differently. Headings such as "AUTHORITY OF HOLY SCRIPTURES AS ORTHODOX CHRISTIAN
DISTINCTIVE" are now one line.

Old and new extractors (`--no-visual-check`) on other local PDFs:

| PDF | Elements | Table cells | Visible characters removed |
| --- | --- | --- | ---: |
| `69-SBLGNT-Galatians.pdf` (8 pp.) | 6,388 → 367 | 6,312 → 0 | 636 |
| `01-SBLGNT-Front.pdf` (23 pp.) | 1,807 → 735 | 1,274 → 32 | 267 |
| `hebrew-40.pdf` | 113 → 53 | 86 → 0 | 0 |
| `aune-3.pdf` (two-column scan) | 176 → 101 | 89 → 0 | 0 |
| `aramaic-25.pdf` | 92 → 66 | 50 → 4 | 0 |
| `semantic.pdf`, `mixed.pdf` fixtures | unchanged | 4, 8 (real tables) | 0 |

Every removed character belongs to an overprinted duplicate fragment: the counts
equal the visible characters in Poppler fragments repeated with the same text and
position (243 on the article). The 32 cells left in the SBLGNT front matter are its
real statistics tables. The 4 on the Aramaic page are OCR noise glyphs from the
scan's hidden text layer. `aune-3` loses three false headings ("to", "of", "Ipa."),
which were isolated noise fragments.

## 2026-11-12: semantic labels from the element review

A visual review of the same article checked every extracted element (669 on 15
pages) and listed 293 wrong labels: running headers, the source footer, footnotes,
section and label headings, bibliography entries and title-page front matter were
all `paragraph`; empty spacers and an overprinted duplicate were kept; a DOI and a
continued page number were list items; a bracketed word was a citation.
`corpora-pdf` now adds a document-level labelling pass and drops blank lines;
pdf-to-tf maps the new labels to `note[@place=foot]`, `fw` and typed `ab` blocks,
and converts with notes included.

| Article run | Before | After |
| --- | ---: | ---: |
| Labels that match the review | 376 / 669 | 669 / 669 |
| Score | 98.68% | 98.73% |
| Lines verified in TF | 569 | 568 |
| `whitespace_element_omitted` notes | 98 | 0 |
| Footnotes (`note`) | 0 | 62 |
| Verification mismatches | 0 | 0 |

The match was checked by pairing each reviewed element with the new element at
the same text and position; the two images are unchanged. The 98 blank spacers are
no longer extracted, and the one fewer verified line is the overprinted duplicate
journal title.

On the other local PDFs (`--no-visual-check`), the new labels are the SBLGNT running
heads ("INTRODUCTION", "ΠΡΟΣ ΓΑΛΑΤΑΣ", verse ranges such as "1:16–2:10") and the
page number on `aune-3`. A publisher imprint at the foot of the SBLGNT title page, a
browser-print line containing "@" on `hebrew-40`, and a lone "." on `aune-3` stay
body text. The `semantic.pdf` and `mixed.pdf` fixtures keep their `h1` title,
including when `mixed.pdf` repeats the page.

### Not established

Only one journal layout was reviewed. Front-matter rules expect a Digital Commons
style cover page; other title pages may keep `paragraph` labels. Footnotes are found
by a rule line or by smaller type at the page foot, not by matching note anchors in
the body.

### Paragraph numbers and reading order

Each `paragraph` line now carries the number of its visual paragraph, and TEI `p`
elements carry it as `@n`. On the article, page 3 lines 2–19 are paragraph 4, and
paragraphs 6 and 10 continue from one page onto the next.

Poppler emitted some lines out of reading order on 10 of the 15 pages: on page 3,
the four lines that open the next paragraph came before the four that end the
current one, and on page 10 a footnote line sat among a paragraph's lines.
`corpora-pdf` now puts each paragraph's lines together, top to bottom. Checked on
the article:

| Article run | Before | After |
| --- | ---: | ---: |
| Pages with paragraph lines out of reading order | 10 | 0 |
| TEI `p` elements for 38 paragraphs | 69 | 47 |
| Labels that match the review | 669 / 669 | 669 / 669 |
| Verification mismatches | 0 | 0 |

The 9 extra `p` elements are paragraphs that continue after a page break; they
share `@n`. Elements, text and labels are unchanged; only their order moved.

Pages where two paragraph lines share a row keep Poppler's order, because there
one element is not one printed line. That is every page of `69-SBLGNT-Galatians.pdf`
and the affected pages of `01-SBLGNT-Front.pdf`, where Poppler leaves printed lines
in pieces at ligatures ("Th", "γγελ"), and it also covers page columns. A first
version without this check scrambled those pieces on 13 pages of the two files.
With it, the extraction of those files, `hebrew-40.pdf`, `aramaic-25.pdf`,
`aune-3.pdf` and the crate fixtures is identical with and without the reordering.

## 2026-11-12: four Academia.edu articles

Four article PDFs with different layouts, image quality and density were converted
with `--languages eng` and checked in the review page. Gate scores did not change,
because they measure text extraction, not labels:

| PDF | Pages | Source | Gate |
| --- | ---: | --- | --- |
| Towards a Nonjuridical Understanding of Episcopal Succession | 17 | book reprint, scan with a text layer | gated, 94.33% |
| Bishop appointing in the patristic time | 24 | born-digital, legacy Greek font | gated, 93.55% |
| Ordination in the New Testament | 5 | two-column scan with hidden OCR | converted, 98.30% |
| Prostitution and the Church in the Homilies | 20 | born-digital student paper | converted, 98.45% |

Labelling problems found and fixed in `corpora-pdf`:

| Problem | Before | After |
| --- | --- | --- |
| Towards: uneven line spacing on the scan split paragraphs | 130 paragraphs | 69 |
| Towards: centred section numbers "1." to "5." | `paragraph` | `h2` (one OCR'd as "4-" stays `h1`) |
| Bishop: running heads and page numbers ending just below the 8.5% band | `h2` / `paragraph` | 46 `running_header` |
| Ordination: a paragraph running from the left column into the right | 2 paragraphs each time | 1 (2 places) |
| Prostitution: page numbers below the footnote rule | `footnote` | 18 `running_footer` |
| Prostitution: cover page lines in capitals | `h2` | `paragraph` |
| Prostitution: bibliography with "Primary" and "Secondary" subheadings | `paragraph` | 62 `reference` |

Checks on earlier inputs: the triadic article's labels and paragraph numbers are
identical to the previous build. SBLGNT Front and Galatians, `hebrew-40.pdf`,
`aune-3.pdf` and the crate fixtures are unchanged. On `aramaic-25.pdf`, two cells of
the vocabulary table are no longer `h2`, which was wrong. Hebrew has no capitals, so
the cells passed the capitals test, but no body text follows them.

### Limits of the source PDFs

- Bishop prints Greek in a legacy font without a Unicode map, so the text layer
  reads "presbutšrion" (626 script findings). This needs a font map, not a
  labelling rule. Its Polish and French summaries (pages 23–24) score low because
  only the `eng` Tesseract model was installed.
- Ordination's hidden OCR layer has garbage such as "ｾＮＭａｴ" in places.
- A body line on Bishop page 20 is still `h3`. The extractor sees it as larger and
  bold, and no document-level rule overrides that yet.
- The Prostitution cover page is plain `paragraph`. It has no issue details, so the
  front-matter rules do not label its title and author.

### Bibliography entries

`reference` lines now carry an `entry` number from their hanging indent, and
pdf-to-tf writes one `bibl[@n]` per entry with its lines as `seg[@type=line]`.
On the triadic article, the 43 bibliography lines on pages 14–15 form 21 entries,
matching the printed page, with 0 verification mismatches; labels and paragraph
numbers are unchanged. The Prostitution bibliography sets every line flush, with
no hanging indent, so it keeps one entry per line (62).
