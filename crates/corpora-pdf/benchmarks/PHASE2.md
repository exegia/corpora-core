# Phase 2: recognizer capability gate

Started 2026-11-10 on `feat/pdf-ocr-phase-2`, from Phase 1 merge `2070422`.
Status: capability/access audit done; first frozen-crop comparison run on
2026-11-11 through Vercel AI Gateway with `anthropic/claude-opus-5.5` (one call).
Hosted recognition uses Vercel AI Gateway only; direct Mistral is not used.
The scope is a dedicated recognizer comparison before a broader acceptance run.

## Frozen first comparison

Use the existing `hebrew-line-18` region, physical page 200, normalized top-left
bounds `[0.23, 0.320, 0.432, 0.346]`. The original PDF SHA-256 is
`6dbaadab22d4ab19928f5ad04a655a70219018689d0dcafd8b28dd36fb1faa42`;
the crop SHA-256 is
`ba9b4f032cb0b56ec73cefef8c9fb5f39ee22b27e1aa6c761f97f46a88b19856`.
Both were rechecked against the source and frozen reference ledger.

The reference requires U+05B0, U+05B2, U+05B6, U+05B7, U+05BB and U+05C1.
It is assistant image-verified, not human specialist approved. Keep the existing
24-codepoint NFD reference and unpointed divine name unchanged. Never provide
the reference, expected marks or previous candidate as recognition hints.

Compare one response with the existing Gemini candidate using base-character
errors, located mark discrepancies, NFD CER and completion status. Retain raw
output even if incorrect; no spelling normalization, reconstructed vowels or
retries until a desirable answer appears. A perfect result on this crop only
qualifies a recognizer for a larger evaluation; it does not accept the model.

## Capability and access findings

| Candidate/route | Evidence checked | Decision |
| --- | --- | --- |
| Rivok `paddleocr-hebrew` | Exact published charset at commit `bf197e94b5ee88ff0c06abeaf9224e8f3eb00210`, SHA-256 `1bdb9e6baaf155ba0661c1a0687bd84ad2bb140a912e0a7c8e5c10eb496b4766`; all six required marks absent. | Disqualified for this pointed-text comparison; no weights downloaded or inference run. |
| Vercel AI Gateway | Public `/v1/models` snapshot contained 505 entries, no IDs containing `ocr`, and no Mistral OCR entry. Documentation search returned general vision/PDF APIs, without establishing a dedicated OCR endpoint. | No dedicated OCR route verified, so comparisons use general vision models through the existing `--provider vercel --gateway-model` path. This is a dated catalog observation. Do not invent a model ID or send a Gateway key to Mistral. |
| Vercel `anthropic/claude-opus-5.5` | Authenticated catalog (`include_availability=true`) reported it ineligible (`model_not_allowlisted`) until the team allowlist was updated on 2026-11-11; then eligible with image input. | Selected as the first Gateway comparator (different model family from the Gemini baseline). |
| Direct Mistral `mistral-ocr-2512` | Dedicated `/v1/ocr` image API; OCR language table lists Hebrew. Closed-model output alphabet and niqqud-specific guarantee were not established. | Not used: project decision to route hosted recognition through Vercel AI Gateway only. The accounting code stays but is not part of this plan. |

Sources checked 2026-11-10:

- [Published Rivok charset at the audited revision](https://github.com/RivoksLab/paddleocr-hebrew/blob/bf197e94b5ee88ff0c06abeaf9224e8f3eb00210/models/charset_v2f.txt)
  and [maintainer's explicit niqqud limitation](https://pypi.org/project/paddleocr-hebrew/).
- [Vercel public model catalog](https://ai-gateway.vercel.sh/v1/models).
- [Mistral OCR language support](https://docs.mistral.ai/resources/languages),
  [image-processing API](https://docs.mistral.ai/studio/document-processing/basic_ocr)
  and [pinned OCR 3 model/pricing](https://docs.mistral.ai/models/ocr-3-25-12).
  Published standard pricing is $2 per 1,000 pages; actual image billing and
  response usage must be recorded rather than inferred from token pricing.

## First comparison result (2026-11-11)

Run: `--provider vercel --gateway-model anthropic/claude-opus-5.5 --max-calls 1`,
fresh cache, no client retry, default reasoning effort. Source and rendered crop
hashes matched the frozen values above. Only the crop and the tool's fixed prompt
were sent. Two earlier attempts stopped at the free eligibility check
(`model_not_allowed`, before and just after the allowlist change) and sent no
inference; they are not retries of a recognition answer.

| Model | Status | NFD CER | Codepoint edits | Mark discrepancies |
| --- | --- | --- | --- | --- |
| `anthropic/claude-opus-5.5` | `review_required`, finish `stop` | 0.000 | 0 | none |
| `google/gemini-3.6-flash` (Phase 1 baseline) | `review_required` | 0.042 | 1 | base 4 (bet): U+05BB missing, U+05B6 inserted |

Reported usage: 216 prompt tokens, 275 completion tokens (246 reasoning).
Gateway returned no cost field; at catalog list prices ($4 / $20 per million
input/output tokens) the estimate is about $0.0064. Wall time, including the
eligibility check and crop rendering, was 6 s.

All six required marks are present and the divine name stays unpointed. This
qualifies Opus 5.5 for the larger evaluation only; it does not accept the model,
and the output stays review-required. The reference is still assistant
image-verified, not specialist approved.

## Next bounded step

1. Visual check of the crop beside the reference, Opus and Gemini candidates.
2. Run the human-reviewed multi-line script benchmark from `agent/PROPOSAL.md`
   with Opus 5.5 and the Gemini baseline through Gateway, with an explicit
   `--max-calls` cap per model. A single perfect crop says little about error rates.

Run the tool with Pillow available, for example
`uv run --no-project --with pillow python crates/corpora-pdf/tools/ocr_review.py ...`;
the macOS system Python has no Pillow and fails before rendering.

Private prepared inputs and audit receipts are under
`target/pdf-benchmark/phase2/`: `hebrew-one-crop-manifest.json`, `preflight.json`,
`paddle-alphabet-audit.json`, `gateway-catalog-audit.json`, `opus55-report.json`
and the local side-by-side page `review/index.html`. No PDF, crop,
transcription, credential or generated candidate is committed. The larger
human-reviewed script benchmark and layout acceptance remain later Phase 2 work
as specified in `agent/PROPOSAL.md`.

## Held-out line benchmark (pre-registered 2026-11-11)

Fixed before any line is selected or sent to a model. Changing a threshold,
metric or model after a run starts needs a new dated section, not an edit here.

### Lines

120 held-out lines, 40 per script, one text line per crop:

| Script | Source | Kind |
| --- | --- | --- |
| Hebrew | Waltke–O'Connor grammar PDF (SHA-256 `6dbaadab…`), quoted pointed examples | Born-digital, BibleWorks `Bwhebb` font |
| Greek | SBLGNT Galatians PDF (SHA-256 `ee9b75cd…`) | Born-digital, polytonic |
| Aramaic | *Basics of Biblical Aramaic* PDF (SHA-256 `46896fb2…`) | Scanned, CVISION text layer |

Spread lines across pages and include varied mark inventories. Exclude every
region already sent to a model (`hebrew-line-18`, `hebrew-line-18b`,
`greek-line-1`, `greek-line-2`, `aramaic-line-1`, `aramaic-line-5`) and any
crop overlapping one. Greek comes from one 8-page, one-font source; its result
does not generalize to other Greek printing.

### References

Draft each reference without any model under test: Hebrew from the decoded
`Bwhebb` text layer, Greek from the PDF text layer, Aramaic from the
Westminster Leningrad Codex verse matched by consonants against the scan's
text layer. Cantillation is kept only when printed in the crop. A person then
checks every draft against its crop and approves, corrects or excludes it with
a reason. Only human-approved lines are scored. If a script ends with fewer than
40 approved lines, report the real count rather than topping up after a run.

### Metrics (NFD, per script, pooled over lines)

- **Completion:** lines with a non-empty `review_required` candidate / lines sent.
- **Base error:** edit distance over base characters (combining marks removed) /
  reference base characters.
- **Mark error:** (missing + inserted combining marks, located per aligned base
  character) / reference marks. Hebrew counts points, dagesh, shin/sin dots and
  printed accents; Greek counts accents, breathings, diaeresis and iota subscript.
- **Divine name:** any mark added to an unpointed tetragrammaton is a violation.

Failed or empty responses count as incomplete and are excluded from the error
rates, which are reported with their line counts.

### Thresholds (strict)

A model passes a script only if all four hold for that script:
completion ≥ 98%, base error ≤ 1%, mark error ≤ 2%, divine-name violations = 0.
Scripts are judged separately; there is no cross-script average.

### Run

Models: `anthropic/claude-opus-5.5` and the baseline `google/gemini-3.6-flash`,
both through Vercel AI Gateway, default reasoning effort, fresh caches.
One request per line, `--max-calls 120` per model, no retries. Expected cost
under $1 at catalog list prices. Passing qualifies a model as a candidate for
that script on these sources only; every output stays review-required.

### Amendment before any inference (2026-11-11)

Recorded during line selection, before references were reviewed or any model
saw a held-out line:

- **Hebrew stress signs.** Waltke–O'Connor prints its own stress signs (a `<`
  above and a `^` below a letter) that have no single Unicode equivalent. Lines
  containing them are not selected, so a correct reading cannot be scored as a
  mark error. Other printed marks, including meteg, are kept.
- **Apostrophe forms.** U+0027, U+2019, U+02BC, U+1FBD and U+1FBF print alike
  in these sources and are folded to one character before scoring. No other
  characters are folded.
- **Aramaic crop frame.** The Aramaic PDF's CropBox (612×792) sits inside a
  larger MediaBox (612×828). `ocr_review.py` renders the MediaBox through
  `pdftoppm`, so Aramaic bounds are expressed in that frame and every crop was
  rendered with the tool's own renderer and hashed. The Hebrew and Greek PDFs
  have identical boxes. Rendering the CropBox in the tool is a separate fix.
- **Selection result.** Hebrew: 40 lines on 40 pages, 4 containing the divine
  name. Greek: 40 lines on all 8 pages (32 main text, 8 apparatus). Aramaic: 40
  word spans of 3–6 words on 40 pages of the annotated text, avoiding verse
  numbers, footnote superscripts and ketiv/qere brackets. Tesseract `heb`
  (not a model under test) only located Aramaic words for WLC alignment.
