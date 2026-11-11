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
