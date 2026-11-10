---
name: pdf-ocr
description: Extract and review PDF text with source-bound OCR diagnostics, specialist script models, bounded hosted fallback, and explicit Hebrew, Aramaic, Greek and Arabic mark uncertainty.
---

# PDF OCR

## When to use

Use for PDF extraction, OCR selection, script/diacritic QA, or preparing a later
consumer review. This skill belongs to `crates/corpora-pdf`; the repository skill
catalogue links to it. It supplements the general `pdf` skill with corpus-fidelity
requirements. Read the crate's `agent/PROPOSAL.md` for scope and `agent/SYSTEM.md`
for the specialist prompt; `benchmarks/HISTORICAL-SCRIPTS.md` contains sources.

## Workflow

1. Inspect source metadata, page count and available embedded text. Preserve the
   original PDF and SHA-256. Render selected pages to inspect visible text; a hidden
   text layer can be corrupt. Embedded-text extraction is not OCR.
2. Retain physical page numbers, source geometry, word boxes and block order.
   Preserve corpus wording, punctuation and combining marks. Do not globally sort
   a multi-column page by y/x or treat inferred tables as verified structure.
3. Identify script/material and a matching model. Check the actual codec before
   accuracy tests, then evaluate the marks on source images. Language support,
   font coverage, model confidence and valid spelling do not establish fidelity.
4. For selected hosted processing, use a pinned model, bounded request count and
   private cache. Keys belong only in the process environment. A cached candidate
   is not an approved correction; preserve raw and proposed readings separately.
5. Emit location-linked review findings and export a draft where allowed. Report
   exact missing accents only with image-verified evidence; otherwise report risk
   and leave the unknown marks null. Later corrections need a source/revision pin.

## Script policy

- Hebrew and Hebrew-script Aramaic: review niqqud, meteg and cantillation. Ordinary
  unpointed text is valid; do not infer lost vowels solely from absent marks.
- Greek: inspect accents, breathings, iota subscript and diaeresis. Evaluate CLLG
  as a candidate, not an accepted default. Latin macrons and editorial signs matter.
- Syriac/Arabic: select the correct script style and mark inventory. Sophro Mhiro
  excludes vowels; broad Arabic support does not certify historical vocalization.
- Ugaritic/Phoenician/cuneiform: distinguish printed signs, Latin transliteration
  and artifact photos. Unsupported regions need source-preserving review, not a
  guessed modern-script transcription.

## Existing verification commands

From the repository root:

```sh
cargo test -p corpora-pdf
python3 -m unittest discover -s crates/corpora-pdf/benchmarks -p 'test_*.py'
python3 -m unittest discover -s crates/corpora-pdf/tools -p 'test_*.py'
python3 -m unittest discover -s tests/browser -p 'test_pdf_review.py'
make agents-check
```

See `tools/README.md` for the source-pinned region manifest and local/Mistral CLI.
Hosted adapter tests do not establish paid-model accuracy; run a separately
reviewed sample before accepting a script/model combination.

## Context and pitfalls

The supplied general `pdf` skill informs tool choice: Poppler/pypdf/pdfplumber for
embedded data, a renderer for pixels, a recognizer for scanned text. PDFluent SDK
is an optional rendering/extraction reference with separate AGPL/commercial terms;
no dependency or code from it is required here. Do not copy proprietary skill text.

Our Tesseract Hebrew model cannot emit holam. Generic Kraken can emit niqqud but
missed both sampled vowels. Preserve these failures as evidence and use human-
verified references for acceptance. Never repair OCR through global replacements.

Keep private sources, references, weights and reports out of Git. Bind the local
HTML review server to loopback. Never expose secrets in reports or tool errors.
