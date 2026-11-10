# Phase 2: recognizer capability gate

Started 2026-11-10 on `feat/pdf-ocr-phase-2`, from Phase 1 merge `2070422`.
Status: capability/access audit complete; no new recognition request made.
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
| Vercel AI Gateway | Public `/v1/models` snapshot contained 505 entries, no IDs containing `ocr`, and no Mistral OCR entry. Documentation search returned general vision/PDF APIs, without establishing a dedicated OCR endpoint. | No supported dedicated OCR route verified. This is a dated catalog observation, not proof that every possible integration is unavailable. Do not invent a model ID or send a Gateway key to Mistral. |
| Direct Mistral `mistral-ocr-2512` | Dedicated `/v1/ocr` image API; OCR language table lists Hebrew. Closed-model output alphabet and niqqud-specific guarantee were not established. Existing adapter pins this version. | Exploratory candidate only; mark capability remains unknown. The local `MISTRAL_API_KEY` is absent. Preserve the existing model pin for the first comparator, rather than silently switching to a newer alias. |

Sources checked 2026-11-10:

- [Published Rivok charset at the audited revision](https://github.com/RivoksLab/paddleocr-hebrew/blob/bf197e94b5ee88ff0c06abeaf9224e8f3eb00210/models/charset_v2f.txt)
  and [maintainer's explicit niqqud limitation](https://pypi.org/project/paddleocr-hebrew/).
- [Vercel public model catalog](https://ai-gateway.vercel.sh/v1/models).
- [Mistral OCR language support](https://docs.mistral.ai/resources/languages),
  [image-processing API](https://docs.mistral.ai/studio/document-processing/basic_ocr)
  and [pinned OCR 3 model/pricing](https://docs.mistral.ai/models/ocr-3-25-12).
  Published standard pricing is $2 per 1,000 pages; actual image billing and
  response usage must be recorded rather than inferred from token pricing.

## Next bounded step

Prepare direct-Mistral response accounting before the paid probe: the existing
adapter returns Markdown only and currently discards provider usage. Preserve
validated page usage and reported model identity in the candidate/cache record,
with credential-free regression tests and compatibility for existing callbacks.
Do not label missing provider accounting as zero cost.

Then, with `MISTRAL_API_KEY` configured locally, run only the frozen region with
`--provider mistral --max-calls 1`, no client retry. Recheck the source and rendered
crop hash before upload, keep credentials in the environment, and send only the
image. Record response status, elapsed time, reported usage and cost assumptions.
Keep the output review-required regardless of score. Inspect it in the internal
browser beside the same source and reference before proposing any model change.

Private prepared inputs and audit receipts are under
`target/pdf-benchmark/phase2/`: `hebrew-one-crop-manifest.json`, `preflight.json`,
`paddle-alphabet-audit.json` and `gateway-catalog-audit.json`. No PDF, crop,
transcription, credential or generated candidate is committed. The larger
human-reviewed script benchmark and layout acceptance remain later Phase 2 work
as specified in `agent/PROPOSAL.md`.
