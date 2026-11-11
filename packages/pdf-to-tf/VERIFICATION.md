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
