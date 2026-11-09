# Attached-PDF pilot — 2026-11-09

Engine checkpoint: `59f954d` (`feat/pdf-ocr-engine`). Benchmark tooling was
uncommitted during this run. Private source manifest and complete evidence:
`target/pdf-benchmark/manifest.local.json` and `target/pdf-benchmark/final/`.
The report records exact binary, script and manifest hashes. No hosted AI was used.

Eight attachments were inventoried; four physical PDF pages were selected.
Seven reference regions contain 413 NFC-normalized characters in total.
References were visually transcribed by the assistant, not independently verified
by a human. These are provisional measurements of small regions, not book-level
acceptance or calibrated accuracy claims. OCR used only installed `eng` data;
Hebrew/Aramaic recognition was not configured.

| Document | PDF page | Native region CER | Raster OCR region CER | Other finding |
| --- | ---: | ---: | ---: | --- |
| Basics of Biblical Aramaic | 25 | 14.29% | Excluded | All three OCR regions cross merged table-row boundaries. Native English cells match; sampled Hebrew/Aramaic words lose marks/direction. |
| Introduction to Biblical Hebrew Syntax | 40 | 1.18% | 2.35% | This sample is English bibliography. Native inserts spacing before a comma; OCR changes en dashes to hyphens. |
| Athanasius, On the Incarnation | 20 | 1.01% | 0.50% | Hidden text reads `contm` for visible `contra`; fresh OCR reads `aud` for `and`. |
| Aune | 3 | 1.15% | 0.00% | Raster text matches sampled wording but fails the left-page-before-right-page order check. |

Page-level engine evidence scores ranged from 89.38% to 99.60% on native
extraction and 92.26% to 94.59% on raster OCR. These scores did not exclude the
observed script, geometry, or reading-order failures. No engine corrections or
acceptance thresholds were added in this benchmark increment.

## Source identities

| Sample | Original PDF SHA-256 |
| --- | --- |
| Aramaic | `46896fb229420e2cdd102fcfc36682547900567284dc0df35efac5a3de3d350c` |
| Hebrew syntax | `6dbaadab22d4ab19928f5ad04a655a70219018689d0dcafd8b28dd36fb1faa42` |
| Athanasius | `f97f7990d5647810ab6c1df1e0e81cbda405533d6bc56b2357f26d77c4f4436c` |
| Aune | `bb74d91732a4b3f97a27fe1f5de97e9032a5ab93f025b4b268f064a26d8b4741` |

## Executed checks

- `python3 -m unittest discover -s crates/corpora-pdf/benchmarks -p 'test_*.py'`:
  10 passing tests, covering edit rates, Unicode marks, missing text, source hashes,
  unsafe/invalid manifest fields, HTML escaping, column order and ambiguous cells.
- Synthetic manifest end-to-end run: native and raster CER/WER both zero; both
  regions spatially bounded; reading order passes; methods are text layer and OCR.
- Attached-document manifest: all four pages processed in both modes; raw JSON,
  rendered images, references and findings retained in the private output.
- Existing browser builder test: 1 passed. `make doctor`, `make fmt`, `make ci`
  and `git diff --check` passed. CI includes all five Rust PDF integration tests.
  Swift checks required execution outside the restricted subprocess sandbox.
- Opened the final report through the integrated browser on loopback port 8773;
  screenshot confirmed the dark page-image/reference/output comparison renders.

## Layout follow-up — 2026-11-09

New evidence: `target/pdf-benchmark/layout-reviewed/`; the original `final/` directory
above remains the baseline. The same manifest, pages, language and references
were used. No transcript was changed to improve a score.

- Aramaic raster OCR: ambiguous regions drop from 3 to 0. English translation
  cells have zero character error; both Hebrew-script words remain incorrect
  with English-only OCR. The now-measurable combined region CER is 14.29%.
- Aune raster OCR: left-page-before-right-page order changes from failing to
  passing; the sampled text remains at zero CER. Tesseract's existing block order
  was correct; the engine's global vertical sort was undoing it.
- All four native page payloads are identical to baseline. Across all four OCR
  pages, word multisets are identical to baseline, with no omissions/duplication;
  new individual word records match the retained text.
- Eight deterministic layout/compatibility regressions plus five real-engine
  integration tests pass. Cases cover repeated cells, isolated wide spaces,
  parallel prose columns, hanging-indent lists, spanning headings/footer, RTL combining marks and
  older JSON without the new `words` field. Clippy passes with warnings denied.

This increment corrects grouping/order, not recognition. Multilingual OCR and
broader human-verified reference coverage remain necessary before quality gates.
