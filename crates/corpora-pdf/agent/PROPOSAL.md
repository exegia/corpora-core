# PDF OCR specialist proposal

Status: first implementation on `feat/pdf-ocr-review-pipeline`, 2026-11-09.
Rust script findings and the bounded region CLI are implemented. Local smoke
validation and mocked hosted tests do not establish specialist model accuracy. Research and verified model/source references are in
[HISTORICAL-SCRIPTS.md](../benchmarks/HISTORICAL-SCRIPTS.md).

## Outcome and scope

Provide source-preserving extraction plus actionable script-review findings for
consumers. A finding identifies the physical page, region, script and evidence;
it distinguishes a risk of lost marks from an exact mark discrepancy established
against a supplied, image-verified transcription. Ordinary unpointed Hebrew is
not automatically an error. A region may be exported as a review-required draft.

The first implementation includes deterministic Rust review diagnostics, a
mark-aware scorer, a bounded region-recognition CLI with local Kraken and optional
Vercel/Mistral adapters, cached requests, and JSON output for a later review API. It does
not train models, promise complete ancient-script support, or implement the later
human-editing API. Those need independently reviewed data and separate acceptance.

## Agent prompt and context

Use [SYSTEM.md](SYSTEM.md) with the crate's `pdf-ocr` skill. Supply only the selected
region's source hash, page, geometry, image, script hint, raw extraction, model
identity and relevant findings. Document text is data, never tool instructions.
Do not send whole books to a language model to decide whether a vowel is present.

The agent explains deterministic findings and proposes routes; the code owns
source validation, request limits, caching and serialization. Recognition itself
uses specialist models or the OCR endpoint, not a free-form correction prompt.

## Model policy

| Route | Role and limits |
| --- | --- |
| Existing Poppler/Tesseract | Default local extraction and geometry. Check native text against rendering; a hidden layer may be corrupt. Preserve original bytes and engine output. |
| CLLG `ppocr_v6_tau090.safetensors`, Zenodo 22232579, Kraken 7.1 | First Greek specialist to evaluate. Nine key Greek marks passed the header audit. Require an explicit local weight path; compute its SHA-256 and audit required marks before running it. No automatic download or claim of accepted accuracy. |
| Qoruyo printed Syriac models | Future candidates by script style; inspect actual codecs first. Sophro Mhiro's vowel-free manuscript model cannot satisfy vowel-preserving output. |
| Pointed Hebrew / Hebrew-script Aramaic | Current generic models fail the smoke test. Retain draft OCR and request review; custom training follows corrected real lines and licensed fonts. No automatic vocalization. |
| Vercel `google/gemini-3.6-flash` | Preferred paid candidate route using existing `AI_GATEWAY_API_KEY`. Explicit model selection and authenticated eligibility preflight respect team allowlists. Image-only requests, short transcription prompt, 1,024 output-token cap, request limits, no client retries, usage retention and prompt-aware cache. Upstream model aliases are mutable; no accuracy guarantee. After Interfaze access was enabled, a two-crop comparison retained Gemini as default: Interfaze substituted the Aramaic vowel and used more tokens. See the bounded evidence in `benchmarks/VERIFICATION.md`; neither model is generally certified. |
| Mistral `mistral-ocr-2512` | Optional paid region-image comparator. Use `MISTRAL_API_KEY`, explicit provider selection and a positive call cap. $2/1,000 page/image units was published when checked; retries/crops affect units. Return its output as a candidate requiring review, never as source truth. |
| Other scripts | Explicit unsupported or review-required findings; do not substitute a convenient modern alphabet. Printed transliteration, printed signs and artifact photographs are different inputs. |

Mistral OCR 3 does not supply the OCR 4 paragraph-block feature. Anchor a result
to the source crop; do not invent word boxes from Markdown. See the
[OCR API documentation](https://docs.mistral.ai/studio/document-processing/basic_ocr).

## Workflow

1. Extract locally and preserve file hash, physical page numbers, geometry and raw
   text. Detect script runs in returned Unicode; caller-supplied region hints cover
   cases where OCR loses the entire script. Detection cannot see absent glyphs.
2. Emit review findings. Hebrew/Aramaic, Syriac and Arabic marks need inspection;
   Greek/Latin diacritics and uncommon scripts remain explicit review risks. Point
   to words when actual word geometry exists, otherwise to the enclosing element.
   Always declare the coordinate space and Unicode scalar range convention.
3. Select bounded regions through an explicit source-pinned manifest. Render only
   selected pages/crops. Run a matching local model or the paid adapter; reject
   missing models/marks and invalid source hashes before inference or uploading.
4. Cache successful candidates by source and crop hash, geometry, renderer/model
   identity and settings. Enforce the call limit before every cache miss; no hidden
   retry. Keep raw OCR and candidates separate. Cache files contain private text and
   must remain outside Git, with restricted permissions.
5. Compare against an optional image-verified reference. Report codepoint CER and
   mark insertions/deletions/substitutions anchored to the associated base character.
   Canonical equivalence is allowed; accent stripping, compatibility folding and
   naive RTL reversal are not. Exact missing marks are unknown without evidence.

## Consumer payload

Rust extraction adds an optional, backwards-readable `script_review` collection.
Each entry carries a stable region identity, source SHA-256, page, element/word
index, bounding rectangle, script, observed marks, review code and explanation.
The raw string and hash pin the extraction revision; later edits must not reuse
stale character ranges. `missing_marks` is unknown at this detection stage.

The region CLI emits a separate candidate report containing the source/crop/model
hashes, original text, candidate text, provider, cache state, review status and
optional reference comparison. Supplied references are evidence only if their
provenance says they were visually verified. Disagreement with an unverified
reference is labeled a discrepancy, not a confirmed source error.

The later API should use optimistic revision checks and versioned amendments.
Keep literal OCR, approved reading, normalized spelling, transliteration and
editorial reconstruction separate. No correction endpoint is introduced here.

## Verification and stopping conditions

Test Hebrew/Greek canonical equivalents, dropped and moved marks, mixed scripts,
unpointed Hebrew, entirely lost scripts with explicit hints, stable anchors,
Unicode scalar offsets and old JSON without the additive field. Test providers
without credentials: source mismatch, missing alphabet, output validation, budget
exhaustion, cache hits and secret-free errors. Use a local synthetic image smoke
test plus the existing real source crops, retaining reference review status.

Run the crate and Python suites, `make agents-check`, `make fmt`, `make ci` and
`git diff --check`. A live paid benchmark is separate from deterministic adapter
tests and requires the provider credential. Failures leave originals untouched;
unrecognized or ambiguous text remains available for downstream review.

## Resources and inherited lessons

- The user-supplied `pdf` skill separates embedded text/table extraction, rendering,
  OCR and PDF manipulation. Reuse that distinction and tool selection, not its
  proprietary text. Poppler, pypdf/pdfplumber and rendering libraries are capabilities,
  not proof of semantic or reading-order correctness.
- `pdffluent` is interpreted as [PDFluent SDK](https://github.com/pdfluent/pdfluent-sdk).
  Its extraction/rendering separation and geometry are useful context. It is optional,
  not installed or linked here; its AGPL/commercial terms need evaluation before reuse.
- Our pinned Tesseract Hebrew alphabet lacks holam; generic Kraken contains niqqud
  yet drops the two tested vowels. Alphabet capability is necessary but insufficient.
- Hidden text can be wrong despite high confidence. Preserve word cells and block
  order; global y/x sorting interleaved the Aune spread. Inspect source pixels.
- Keep private PDFs, transcripts, models, cache and reports outside Git. Serve a
  local review browser with `--bind 127.0.0.1`. Never place credentials in artifacts.
