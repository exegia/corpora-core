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

The preferred paid route uses your existing Vercel AI Gateway key:

```sh
python crates/corpora-pdf/tools/ocr_review.py source.pdf manifest.json vercel-report.json \
  --cache target/pdf-benchmark/review-cache --provider vercel --max-calls 2
```

Set `AI_GATEWAY_API_KEY` in the process environment. The CLI does not automatically
load `.env`; your launcher must load it without exposing its values. No separate
Mistral account or key is needed for this route.

The adapter calls the [Gateway Chat Completions API](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions)
with `google/gemini-3.6-flash`, a 1,024-token output cap and no client retries.
Use `--gateway-model provider/model` to explicitly select a different vision model.
The first uncached region triggers one authenticated, read-only catalog check
(`include_availability=true`); ineligible models fail before inference. Gateway
uses the team's permitted providers; this tool does not change team policy. Only the crop and a short transcription prompt
are sent, never raw OCR or reference transcriptions. The model alias can
change upstream; its identifier is not an immutable weight revision. Cache provenance
includes the request/prompt hash. Clear the private cache for a fresh upstream
model evaluation. A cache hit makes no new paid request.

Gateway candidates retain allowlisted reported token counts in
`recognition_metadata.usage`; cached counts describe the original recognition,
not new spend. Missing usage stays unknown. Counts do not constitute an invoice.
Rejected JSON responses also retain safe accounting under `recognition_metadata`,
including reported `completion_tokens_details.reasoning_tokens` and
`prompt_tokens_details.cached_tokens`. Only nonnegative integer counters are kept;
booleans, strings and invalid counters are omitted. Known finish reasons are kept;
unrecognized values become `unknown`. Missing usage is an empty object, not zero.
Partial text, reasoning text and refusal messages are never saved for rejected
responses, and failures still consume the request budget without creating a
successful cache entry. HTTP/transport failures without usable accounting remain
unknown. Earlier reports cannot recover discarded usage retroactively.
Truncated, refused, tool-call and malformed responses are rejected. Safe error
codes and HTTP status are reported without provider error bodies or credentials.
`provider_not_allowed` and `model_not_allowed` identify configured access restrictions;
`no_providers_available` retains a safe Gateway error type if routing changes after
preflight. `preflight_requests` counts read-only checks separately from inference.
Cached candidates do not require a new eligibility check or credential.
No alternate model is silently substituted. Hosted model-internal routing is
outside this client's control; results still require image review.

### Explicit reasoning effort

On 2026-11-10 the public Gateway catalog advertised `low` and `high` effort for
`google/gemini-3.6-flash`; it did not advertise `minimal` or a numeric reasoning
budget. The [Gateway reasoning API](https://vercel.com/docs/ai-gateway/sdks-and-apis/openai-chat-completions/reasoning)
and [Google mapping](https://vercel.com/docs/ai-gateway/models-and-providers/reasoning/google)
document the raw Chat Completions body extension `"reasoning": {"effort": "low"}`.
Hiding reasoning with `exclude` does not disable internal reasoning.

The adapter leaves reasoning effort unspecified by default and retains its
1,024-token output cap. To explicitly request a supported effort:

```sh
python crates/corpora-pdf/tools/ocr_review.py source.pdf manifest.json low-report.json \
  --cache target/pdf-benchmark/review-cache --provider vercel --max-calls 2 \
  --gateway-reasoning-effort low
```

The CLI accepts `low` or `high` only with `--provider vercel`. Before inference,
the authenticated catalog must explicitly advertise that effort for the selected
model; missing/unsupported capability fails as `reasoning_effort_not_supported`
without an inference call. The option is sent as `reasoning.effort` and changes
the request hash/cache identity. Omitting it preserves the original wire request
and cache identity, including the existing callback signatures for injected
adapters. Cached candidates need no capability check or credentials. An explicit
effort does not guarantee accuracy or the provider's actual reasoning-token use.
Do not infer that the previous failures were truncation: their actual finish
reasons were lost. See `benchmarks/VERIFICATION.md` for the bounded comparison.

The optional direct route uses Mistral OCR 3 (`mistral-ocr-2512`). Set `MISTRAL_API_KEY` in the
process environment, then explicitly choose it:

```sh
python crates/corpora-pdf/tools/ocr_review.py source.pdf manifest.json report.json \
  --cache target/pdf-benchmark/review-cache --provider mistral --max-calls 2
```

Direct Mistral responses retain `recognition_metadata.requested_model`, the
validated `reported_model` identifier when supplied, and `usage_info` with
nonnegative integer `pages_processed` and `doc_size_bytes` counters. These fields
follow the [OCR response contract](https://docs.mistral.ai/api/endpoint/ocr).
Reported model names accept dated Mistral OCR IDs or `latest`, including the
documented `-completion` suffix; unrecognized strings are omitted. Requested and
reported identities remain separate and are not proof of transcription accuracy.

Accounting survives successful cache replay and rejection of a parsed response
with invalid page content. Blank, oversized, malformed or multi-page candidates
are never cached. Provider error bodies and arbitrary response fields are not
retained. Absent/null/invalid counters stay unknown (omitted or `{}`), not zero;
transport errors and unparseable responses cannot supply usage. These are page
and byte counts, not Gateway token counts or an invoice. Cached counts describe
the original request and must not be summed as new spend.

Existing caches without metadata still load without paid refetches. The Python
`hosted(image)` compatibility wrapper still returns Markdown; the pipeline uses
`hosted_response(image)` to retain accounting and still accepts string-returning
custom callbacks. Neither the pinned model, wire request nor cache identity changes.

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
