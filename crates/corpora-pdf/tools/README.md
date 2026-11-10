# Bounded OCR candidate review

`ocr_review.py` renders selected PDF regions and returns separate OCR candidates.
The source PDF and raw extraction remain unchanged. All candidates require image
review, including cached results and reference matches. There is no correction API.
The Rust extractor also emits `script_review` findings; the PDF QA browser displays
them alongside existing findings.

## Manifest

Use an ignored private directory such as `target/pdf-benchmark/review-pipeline`.
Hash the original PDF with `shasum -a 256`. Physical page numbers start at one;
`bounds` is `[left, top, right, bottom]` normalized to the displayed page, with its
origin at the top left. Select one text line per local Kraken region.

```json
{
  "source_sha256": "REPLACE_ME",
  "regions": [{
    "id": "page25-word1",
    "page": 25,
    "bounds": [0.32, 0.117, 0.39, 0.14],
    "script": "hebrew",
    "direction": "R",
    "raw_text": "לא",
    "required_marks": "ָֹ",
    "reference": {"text": "לֹא", "status": "unreviewed"}
  }]
}
```

`reference` is optional. Set its status to `image_verified` only after independent
transcription against the image. Without that evidence, mark differences are
unconfirmed. Required marks are literal Unicode combining characters checked against
the installed local model's codec; specify every mark needed for the intended task.
The local adapter also checks the complete configured base-letter inventory for
each selected script before rendering. Local Ugaritic/Phoenician/cuneiform requests
are rejected until a validated alphabet policy is supplied. Alphabet support does
not establish accuracy. A script hint is required even if OCR
lost all text. Scripts: `hebrew`, `aramaic`, `greek`, `latin`, `arabic`, `syriac`,
`ugaritic`, `phoenician`, `cuneiform`; this is an input taxonomy, not model certification.
Greek/Latin default to left-to-right; others default to right-to-left. Override the
local model direction explicitly for sources with different conventions.

## Running

Use Python 3.10+ with Pillow installed, Poppler's `pdftoppm`, and an isolated
Kraken 7.1 installation for local inference. Models are never downloaded by the tool.

```sh
python crates/corpora-pdf/tools/ocr_review.py source.pdf manifest.json report.json \
  --cache target/pdf-benchmark/review-cache --provider local --max-calls 2 \
  --model /path/to/model.safetensors --kraken /path/to/venv/bin/kraken
```

The paid route uses Mistral OCR 3 (`mistral-ocr-2512`). Set `MISTRAL_API_KEY` in the
process environment, then explicitly choose it:

```sh
python crates/corpora-pdf/tools/ocr_review.py source.pdf manifest.json report.json \
  --cache target/pdf-benchmark/review-cache --provider mistral --max-calls 2
```

Only selected crop images are uploaded. There are no hidden retries; failed attempts
consume the per-run request budget. A cap counts requests, not a guaranteed invoice
amount. Successful cache hits consume no requests. Provider failures and exhausted
budgets retain source information in the report and return exit code 1. Invalid
input or unavailable local tools return 2. Ordinary review-required candidates
return 0; that does **not** mean the transcription has been accepted.

The cache pins source/crop hashes, page/bounds, renderer version, model identity and
direction. Reference edits reuse recognition and recompute comparison. Files are
written atomically with mode 0600; keep their directories private and outside Git.
The cache and report contain private source text. Credential values and provider
error bodies are never serialized. The hosted endpoint is fixed and redirects are
rejected. No hosted request is made by the test suite.

## Consumer contract

Rust findings carry `region_id`, source/text hashes, one-based page, zero-based
element/word indexes, `bounds` in `poppler_108_dpi_top_left` coordinates and half-open
Unicode scalar ranges into `raw_text`. Word geometry is used only when present;
otherwise the rectangle encloses an element. `missing_marks` stays null. Detection
cannot see a completely lost script: use explicit manifest hints for those regions.
Old JSON without `script_review` remains readable. Adding a public Rust struct field
requires downstream struct-literal constructors to supply it.

Candidate reports preserve raw text separately from candidate text, its format,
source location, hashes, cache state and review status. Mistral returns Markdown;
this is preserved literally and never treated as word-level geometry. Comparing a
Markdown candidate against a plain reference can count formatting as text edits.
Select short line crops and inspect those differences.

Reference comparison uses NFD, without stripping accents, compatibility folding or
RTL reversal. It reports codepoint edits/CER and mark discrepancies anchored to
aligned base characters. Moved marks produce a deletion and insertion; substitutions
record both missing and inserted marks. Indexes refer to NFD base clusters, not raw
text offsets. Alignments exceeding one million raw character-pair cells are left unscored with
`comparison_limit_exceeded`; choose a smaller crop. Repeated bases can make an edit
alignment ambiguous, so the actual
image remains necessary. `confirmed_discrepancy` requires an image-verified reference.
No result automatically changes a source or marks a candidate approved.

```sh
python3 -m unittest discover -s crates/corpora-pdf/tools -p 'test_*.py'
cargo test -p corpora-pdf
```
