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
  have identical boxes. The whole Poppler pipeline (extractor, QA browser, OCR
  tool) uses the MediaBox consistently; the tool now records both boxes per
  region and flags pages where they differ.
- **Selection result.** Hebrew: 40 lines on 40 pages, 4 containing the divine
  name. Greek: 40 lines on all 8 pages (32 main text, 8 apparatus). Aramaic: 40
  word spans of 3–6 words on 40 pages of the annotated text, avoiding verse
  numbers, footnote superscripts and ketiv/qere brackets. Tesseract `heb`
  (not a model under test) only located Aramaic words for WLC alignment.
- **Scoring code.** `heldout_score.py` implements these metrics and thresholds
  (tests: `test_heldout_score.py`) and was committed before the run.

## Held-out benchmark result (2026-11-11)

**Reference review.** A first pass approved all 120 drafts in five minutes
(about one second per Aramaic line). That pace cannot verify cantillation, so
the Aramaic lines and one unreviewed Hebrew line were reviewed again before
any inference (about ten seconds per line). Six Aramaic lines were excluded
because the print does not match the WLC draft. Scored: Hebrew 40, Greek 40,
Aramaic 34. No reference was corrected; Hebrew and Greek drafts come from the
PDFs' own text layers.

**Run.** Both models through Vercel AI Gateway, one request per line, no retries,
default reasoning effort, the tool's fixed `max_tokens` of 1024. 228 requests.

| Model | Script | Completed | Base error | Mark error (missing + inserted / marks) | Divine name | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `anthropic/claude-opus-5.5` | Greek | 40/40 | 0.15% | 0.0% (0 / 504) | 0 | **pass** |
| `anthropic/claude-opus-5.5` | Hebrew | 39/40 | 0.76% | 7.6% (32 / 422) | 0 | fail |
| `anthropic/claude-opus-5.5` | Aramaic | 32/34 | 1.11% | 12.2% (100 / 817) | 0 | fail |
| `google/gemini-3.6-flash` | Greek | 23/40 | 0.83% | 0.8% (2 / 262) | 0 | fail |
| `google/gemini-3.6-flash` | Hebrew | 27/40 | 2.01% | 11.1% (31 / 280) | 2 | fail |
| `google/gemini-3.6-flash` | Aramaic | 7/34 | 1.86% | 32.4% (46 / 142) | 0 | fail |

Error rates cover completed lines only. Every incomplete line, for both models,
stopped at the 1024-token output cap (`finish_reason: length`), mostly spent on
reasoning; Gemini lost 57 of 114 lines this way. The cap was not raised during
the run. Gemini's error rates rest on fewer lines and are not comparable to
Opus's at equal coverage.

Opus mark errors: in Hebrew, mostly missing holam (7) and dagesh (5) and inserted
meteg (6); in Aramaic, cantillation accents swapped or dropped (qadma, revia,
pashta, munah, ole) and meteg. Encoding variants (for example holam on vav) were
not inspected line by line and may account for part of the Hebrew holam count.

Usage: Opus 31,116 prompt and 46,692 completion tokens (about $1.06 at catalog
list prices); Gemini 130,011 and 112,815 (about $0.52). The total of about $1.58
exceeds the pre-registered estimate of under $1. Gateway returned no cost field.

**Conclusion.** Opus 5.5 qualifies as a recognition candidate for SBLGNT-style
born-digital Greek only. Neither model meets the thresholds for pointed Hebrew or
cantillated Aramaic; marks remain the blocker. All outputs stay review-required.
A follow-up with a higher, pre-registered output cap would separate completion
failures from reading errors; it needs its own dated section before it runs.
Private inputs, crops, ledger, reports and `runs/score.json` are under
`target/pdf-benchmark/phase2/heldout/`.

## Higher output cap rerun (pre-registered 2026-11-11)

Fixed before any request of this rerun is sent. It measures whether the first
run's incomplete lines were limited by the 1024-token output cap rather than by
the models' reading. It does not replace the first result, which stands as
recorded above; both are reported side by side.

Unchanged from the first run:

- **Lines and references.** The same 114 human-approved lines (Hebrew 40,
  Greek 40, Aramaic 34) and the same reviewed references in
  `reference-ledger.json`. No line is added, removed or re-reviewed.
- **Metrics, thresholds and scorer.** As in "Held-out line benchmark" and its
  amendment, computed by the committed `heldout_score.py` without changes.
- **Models.** `anthropic/claude-opus-5.5` and `google/gemini-3.6-flash`, through
  Vercel AI Gateway only, default reasoning effort, the same prompt.
- **Requests.** One request per line, no retries, `--max-calls 40` per script
  per model, fresh caches (new cache directories; no first-run cache is read).

Changed: the output cap is 4096 tokens (`--gateway-max-tokens 4096`), which both
models' authenticated catalog entries advertise as within their limits
(128,000 and 64,000). The cap changes the request hash, so no first-run
candidate can be reused.

Spend. Worst case at catalog list prices is about $1.9 for Gemini and $9.5 for
Opus if every line used the full cap; the first run's usage suggests about $2–3
in total. Gemini runs first, then Opus, each in the order Hebrew, Greek, Aramaic.
Before each Opus script, if the cumulative estimate plus that script's worst case
(40 × 4096 output tokens) would exceed $8, that script and later ones are not
run; they are reported as skipped and not run later under this section.

Reading the result. If incomplete lines fall to near zero, the first run's
completion failures were budget-limited, and the completed-line error rates of
this run are the better estimate of reading accuracy. Lines that still stop at
`finish_reason: length` under 4096 tokens are reported as completion failures of
the model at this cap, not retried. Passing still qualifies a model only as a
review-required candidate for that script on these sources.

## Higher output cap result (2026-11-11)

**Run.** As pre-registered: the same 114 lines and references, both models through
Vercel AI Gateway only, default reasoning effort, `--gateway-max-tokens 4096`,
one request per line, no retries, fresh caches, Gemini first. 228 inference
requests and 6 read-only catalog checks. No combination was skipped by the
spend rule. The catalog check confirmed 4096 within each model's advertised
limit before inference.

| Model | Script | Completed | Base error | Mark error (missing + inserted / marks) | Divine name | Result |
| --- | --- | --- | --- | --- | --- | --- |
| `anthropic/claude-opus-5.5` | Greek | 40/40 | 0.15% | 0.0% (0 / 504) | 0 | **pass** |
| `anthropic/claude-opus-5.5` | Hebrew | 40/40 | 0.59% | 5.3% (23 / 435) | 0 | fail |
| `anthropic/claude-opus-5.5` | Aramaic | 34/34 | 0.00% | 11.6% (100 / 865) | 0 | fail |
| `google/gemini-3.6-flash` | Greek | 39/40 | 0.62% | 0.0% (0 / 489) | 0 | fail (completion) |
| `google/gemini-3.6-flash` | Hebrew | 33/40 | 13.33% | 6.9% (24 / 350) | 0 | fail |
| `google/gemini-3.6-flash` | Aramaic | 19/34 | 5.56% | 32.5% (157 / 483) | 0 | fail |

Compared with the 1024-token run:

| Model | Script | Completed 1024 → 4096 | Base error | Mark error | Divine name | Result |
| --- | --- | --- | --- | --- | --- | --- |
| Opus 5.5 | Greek | 40 → 40 | 0.15% → 0.15% | 0.0% → 0.0% | 0 → 0 | pass → pass |
| Opus 5.5 | Hebrew | 39 → 40 | 0.76% → 0.59% | 7.6% → 5.3% | 0 → 0 | fail → fail |
| Opus 5.5 | Aramaic | 32 → 34 | 1.11% → 0.00% | 12.2% → 11.6% | 0 → 0 | fail → fail |
| Gemini 3.6 Flash | Greek | 23 → 39 | 0.83% → 0.62% | 0.8% → 0.0% | 0 → 0 | fail → fail |
| Gemini 3.6 Flash | Hebrew | 27 → 33 | 2.01% → 13.33% | 11.1% → 6.9% | 2 → 0 | fail → fail |
| Gemini 3.6 Flash | Aramaic | 7 → 19 | 1.86% → 5.56% | 32.4% → 32.5% | 0 → 0 | fail → fail |

**Completion.** Opus completed all 114 lines; its largest completion was 1,112
tokens, so its 3 first-run failures were budget-limited. Gemini completed 91 of
114 (57 at 1024). All 23 remaining Gemini failures again ended with
`finish_reason: length`, each at 4,092 completion tokens. Reasoning was 97.9% of
Gemini's completion tokens, and its completed Hebrew and Aramaic lines used a
median of 3,342 and 3,964, close to the cap. Gemini's failures therefore stay
budget-limited at 4096 under default reasoning effort.

**Reading.** On the lines completed in both runs (a secondary comparison, not
pre-registered), Opus Hebrew mark error was 7.6% then 5.5% (39 lines) and Opus
Aramaic 12.2% then 11.3% (32 lines); its marks fail either way. The Gateway
catalog lists Opus as not accepting `temperature`, so these differences are
run-to-run variation as much as an effect of the cap. Gemini's Hebrew base
error comes mostly from one line where it returned the reference reading plus
three further lines of other text (66 base edits); without that line it is
1.48%, still above 1%. Gemini Greek misses only on completion (97.5% < 98%).
Gemini's two first-run divine-name violations did not recur.

**Usage.** Opus 31,116 prompt and 44,820 completion tokens (38,725 reasoning),
about $1.02 at catalog list prices, 13 minutes. Gemini 130,011 prompt and
318,291 completion tokens (311,576 reasoning), about $1.29, 38 minutes. Total
about $2.31, within the pre-registered $2–3 estimate. Gateway returned no cost
field.

**Conclusion.** The first result stands, and this rerun does not change any
pass or fail. Opus 5.5 remains a candidate for SBLGNT-style born-digital Greek
only. For pointed Hebrew and cantillated Aramaic its errors are reading errors
in the marks, not completion failures. Gemini 3.6 Flash still cannot be judged
fairly at 4096 tokens with default reasoning, because a fifth of its lines run
out of budget. A further Gemini run, with a larger cap or an explicit lower
reasoning effort, needs its own dated section. All outputs stay review-required.
Reports, `score.json`, `summary.json` (per-report status, finish reasons,
tokens, time, cost) and `matched.json` are under
`target/pdf-benchmark/phase2/heldout/runs-cap4096/`.
