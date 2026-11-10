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

## Multilingual model selection prerequisite — 2026-11-09

The engine and benchmark now accept an explicit traineddata directory. The
benchmark records each requested model's SHA-256. The engine checks requested
languages and rejects Tesseract's otherwise successful fallback when a companion
model fails to load. A native text page retains its text but receives no visual
score and a finding when OCR is unavailable; a scanned page fails extraction.

Executed: 16 Rust tests (including isolated model-directory, missing companion
and corrupt companion cases), 12 benchmark tests, the browser test, `make fmt`,
`make ci`, and `git diff --check` passed. The synthetic benchmark using the
explicit installed English model directory has zero CER in both paths and
retains its model hash under `target/pdf-benchmark/model-provenance-smoke/`.

No Hebrew accuracy result is available for this increment. Only `eng` and `osd`
were installed, and DNS resolution failed for `github.com`, `api.github.com`, and
`raw.githubusercontent.com`, preventing the official Hebrew model download.
The next controlled comparison should hold the English model fixed while adding
Hebrew, retaining vowel marks in the reference metrics. No models were downloaded
or machine-wide OCR configuration changed during this increment.

## Controlled multilingual comparison — 2026-11-09

Connectivity recovered. Downloaded official `tessdata_best` English and Hebrew
models plus their license at revision
`e12c65a915945e4c28e237a9b52bc4a8f39a0cec` into ignored
`target/pdf-benchmark/models/tessdata-best-e12c65a91594/`. System OCR models and
the default engine language were not changed.

| Model | SHA-256 |
| --- | --- |
| eng | `8280aed0782fe27257a68ea10fe7ef324ca0f8d85bd2fd145d1c2b560bcb66ba` |
| heb | `dbaa827aea6bc21215638447f17783a1004987c2d0bf5573d111fee397abdae5` |

Ran `eng`, `eng+heb`, and `heb+eng` against the unchanged three regions on
Aramaic grammar PDF page 25. Verified identical manifest, benchmark, engine binary
and English model hashes across all three runs. Evidence directories are
`best-english/`, `best-english-hebrew/`, and `best-hebrew-english/` beneath
`target/pdf-benchmark/`; `multilingual-comparison/` links the reports and retains
the controlled comparison JSON.

Both multilingual orders recover the two sampled Hebrew-script words' consonants
but omit their vowel marks: each bounded word has 33.33% CER (one missing mark
out of three reference characters). Both also merge English table regions,
making that region's text score ambiguous. English-only bounds the English
region correctly but misrecognizes the Hebrew word and leaves the Aramaic word
region ambiguous. Only **one three-character Hebrew reference** is spatially
bounded in all three runs; its CER is 100% for English-only and 33.33% for either
multilingual order. Different aggregate coverage must not be presented as a
whole-sample accuracy improvement. All references remain visually transcribed
by the assistant and unverified by a human.

The raster extraction times in this single run were 2.70s (`eng`), 3.17s
(`eng+heb`), and 3.27s (`heb+eng`), including subprocess overhead. These are
observations, not statistically established throughput measurements.

Extracted the pinned Hebrew model's `lstm-unicharset` with `combine_tessdata -e`.
The NFC/NFD-equivalent output alphabet contains qamats (U+05B8), which the model
missed here, but does not contain holam (U+05B9). The extracted character-set
SHA-256 is `196ecddf7ce0cf378fa128d121da5eafce863a4c834bdd10c3e6a9265054a336`.
The model therefore cannot supply the holam required by the sampled reference.

Conclusion: explicit multilingual model selection works, but this pinned model
does **not** meet pointed Hebrew/Aramaic transcription requirements. Keep default
behavior unchanged. The next recognition candidate must support the required
vowel-mark alphabet and be tested against a larger independently verified sample;
language-order changes alone did not fix the observed failures.

## Pointed-Hebrew alphabet gate and recognition smoke test — 2026-11-09

Screened alternatives before installing another runtime. The
[PaddleOCR Hebrew model](https://github.com/RivoksLab/paddleocr-hebrew) explicitly
excludes niqqud and cantillation from its alphabet. The
[BGU pointed-Hebrew OCR project](https://www.cs.bgu.ac.il/~elhadad/hocr/) documents
training visual recognition, but its page provides no downloadable trained
weights to audit. Its separate automatic vocalization task is not a substitute
for reading marks from page pixels.

Audited the actual safetensors `kraken_meta` codec of
[Kraken PP-OCRv6 medium](https://huggingface.co/small-models-for-glam/kraken-ppocrv6-medium),
revision `f7fd70f3fd22b615f41bada4674ac2462f938339`, before inference. The model
card describes multilingual Hebrew recognition, not a pointed-Hebrew accuracy
guarantee. Its 1,622 codec labels contain, after Unicode NFD decomposition:

- All 27 Hebrew letter forms and all 17 niqqud characters: U+05B0–U+05BC,
  U+05BF, U+05C1, U+05C2 and U+05C7, including holam.
- Only three of 30 cantillation accents: U+0593, U+0594 and U+059A.
- Upper dot U+05C4, but not meteg U+05BD, lower dot U+05C5 or masora circle U+05AF.

This passes a vowel-only alphabet gate, not complete Biblical-mark preservation.
Downloaded weights SHA-256:
`15313b51ace64cbfa81f8f6ef25ad64f04e5a6fb7f7823e67b107527bc081ac9`.
The full model header matched the previously fetched metadata header. Alphabet,
source revision and weight evidence are under ignored
`target/pdf-benchmark/models/kraken-ppocrv6-medium/`.

Installed Kraken 7.1 in an isolated benchmark virtual environment, then ran CPU
FP32 recognition on the **two unchanged word regions**, cropped from the existing
2400px page raster. Used `ocr --no-segmentation --base-dir R --num-line-workers 0`;
no binarization, dictionary, spellcheck or vowel-restoration postprocessing.

Both outputs contain only the two consonants: the holam and qamats were omitted.
Each word therefore has one edit in three reference characters (33.33% CER).
The alphabet's ability to emit a mark did not establish visual recognition of it.
These are six reference characters in total, with assistant-transcribed references
still unverified by a human. Cropped recognition bypasses page segmentation and
must not be presented as a controlled end-to-end improvement over Tesseract.

Exact command, input crop coordinates/hashes, model audit, runtime package list,
outputs and dark comparison HTML are retained in ignored
`target/pdf-benchmark/kraken-pointed-smoke/`. Both inference jobs completed
successfully; their transcription result fails the pointed-word smoke test.
No production engine, default OCR language or system model directory changed.

A user-supplied font is unnecessary for evaluating existing scanned pages.
For subsequent synthetic training, a font matching the source's letterforms and
mark positioning would help, provided its license permits that use. Synthetic
examples must remain separate from held-out real-page evaluation. This candidate
needs pointed-text fine-tuning or replacement before a larger acceptance run.

## Vercel Gateway adapter and bounded live preflight

The `--provider vercel` adapter requests `interfaze/interfaze-beta` through the
Gateway Chat Completions endpoint. It sends the selected image plus a transcription
prompt, without reference text, and limits output to 1,024 tokens. Requests have
no client retries or alternate-model fallback. Prompt/settings identity separates
its cache from local and Mistral results; reported usage is retained on success.

The first live run attempted the two existing Hebrew/Aramaic regions with a
two-request cap. Both returned HTTP 403 and yielded no candidate text or usage.
A separate read-only credits endpoint request returned HTTP 200 with the same
credential. This establishes that the read-only endpoint accepted the credential;
it does not identify why inference was forbidden or establish model accuracy. No
additional inference requests were made. Inspect Gateway request/access diagnostics
before another explicitly bounded run.

The private failure report is
`target/pdf-benchmark/review-pipeline/vercel-report.json`; original PDFs, local
candidates and unreviewed reference status remain unchanged. No provider error
body or credential is included in the report. Eighteen credential-free OCR tests,
Ruff, strict mypy on both adapter files, `make fmt`, `make ci`, and agent validation
passed. Live hosted accuracy remains unmeasured.

## Gateway routing diagnosis and successful permitted-model smoke

A separately authorized one-crop diagnostic exposed `no_providers_available`: the
evaluated team's Provider Allowlist excludes Interfaze. The authenticated catalog
confirmed `no_allowlisted_provider`. Its credits endpoint succeeding did not imply
permission to use every model. No team access settings were changed.

The adapter now checks authenticated model eligibility before the first uncached
inference and supports explicit `--gateway-model` selection. The default is
`google/gemini-3.6-flash`, the newest eligible standard Gemini Flash version in the
evaluated team's catalog at this run; later Flash versions were not allowlisted.
Model selection and prompt/settings are part of cache identity. Errors retain
allowlisted type codes without arbitrary provider messages or credentials.

Two crop calls through this permitted model succeeded. Each returned all three
reference codepoints, retaining the Hebrew holam and Aramaic qamats that local
Kraken omitted. Each had zero NFD codepoint edits against its existing reference.
References remain `unreviewed`; this six-reference-character sample does not
establish general Hebrew/Aramaic accuracy, Greek accuracy or production acceptance.

Reported usage was 2,336 prompt tokens and 667 completion tokens (3,003 total).
At the observed catalog rates of $0.75/M input and $3.75/M output, the estimated
list-price equivalent is $0.00425325, not an invoice. Private successful and cached
reports are `target/pdf-benchmark/review-pipeline/vercel-gemini-report.json` and
`vercel-gemini-cached-report.json`. The original failed report is retained.

The credential-free suite now has 22 tests, including ineligible model preflight
with zero inference calls, selected-model cache separation and safe error types.

## Interfaze comparison after access was enabled (2026-11-10)

After the user enabled Interfaze in the team settings, authenticated eligibility
reported `eligible`. A separately authorized run selected
`--provider vercel --gateway-model interfaze/interfaze-beta --max-calls 2` on the
same two source-pinned crops. It made one eligibility check and two inference
requests, with no client retries, taking 141.64 seconds including rendering and
preflight. Both requests returned complete candidates.

Assistant visual inspection of the rendered source crops confirmed holam
(`U+05B9`) on the Hebrew lamed and qamats (`U+05B8`) on the Aramaic lamed.
This is assistant image review, not human specialist sign-off. The original
unreviewed manifest/reports remain intact. A separate private manifest records
`image_verified` references, with reviewer identity, source/crop hashes, page,
bounds and observations in `image-review.json`.

| Candidate | Hebrew crop | Aramaic crop | Prompt / completion tokens | Estimated USD |
| --- | --- | --- | --- | --- |
| Gemini 3.6 Flash, previous run | Exact match | Exact match | 2,336 / 667 | $0.00425325 |
| Interfaze beta, this run | Exact match | Qamats replaced by holam | 19,154 / 181 | $0.0293645 |

Interfaze made one NFD codepoint substitution across six reference codepoints
(16.67% combined CER; 33.33% on the Aramaic crop). Its Aramaic candidate is a
confirmed discrepancy against the assistant image-verified reference: missing
`U+05B8`, inserted `U+05B9` at base index zero. This is a two-word smoke test,
not a general accuracy estimate for any language, script or model.

Costs use the public [Gateway model catalog](https://ai-gateway.vercel.sh/v1/models)
observed on this date: Interfaze $1.50/M input and $3.50/M output, Gemini $0.75/M
input and $3.75/M output. They are list-price estimates from reported usage, not
invoices. No claim is made about why Interfaze reported more input tokens.

Rescoring both models against the inspected references used their existing caches:
zero inference calls and zero preflight requests, with the credential removed and
network callbacks set to fail if invoked. Candidates still require review and
never replace source text. Gemini remains the default; Interfaze remains an
explicit option. Broader acceptance needs independently reviewed lines with more
marks and mixed-script layouts.

Private evidence remains under `target/pdf-benchmark/review-pipeline/`:
`vercel-interfaze-report.json`, `manifest-image-verified.json`, `image-review.json`,
and `vercel-{interfaze,gemini}-verified-cached-report.json`. Source PDFs, crop
images, reference transcriptions and cache files are excluded from Git.

Validation: 22 credential-free OCR tests, 12 benchmark tests, two PDF browser
tests, Ruff and strict mypy on both adapters (using the Pillow-equipped OCR
environment), `make doctor`, `make fmt` and `make ci` passed. The required CI run
includes agent validation and Rust/Swift checks.

## Six-line Gemini benchmark (2026-11-10)

The next bounded evaluation used `google/gemini-3.6-flash` on six short line
crops: two Hebrew lines from physical page 200 of the supplied Hebrew syntax
PDF, two Aramaic lines from physical page 137 of the supplied Aramaic grammar,
and two Greek lines from physical page 2 of the publisher's
[SBLGNT Galatians PDF archive](https://www.sblgnt.com/download/SBLGNTpdf.zip).
The Greek samples are clean digital print, not evidence of scanned-Greek
performance. They retain accents, breathings and iota subscripts in the reference.
SBLGNT is copyright 2010 Society of Biblical Literature and Logos Bible Software;
the private viewer links the required attribution. Source files remain outside Git.

References were frozen before inference, with source/crop hashes, physical page,
normalized bounds and reviewer identity. Two assistants independently inspected
the pixels; this is not human specialist sign-off. Five references are
`image_verified`. One Aramaic reference remains `unreviewed` because a tiny speck
inside bet might be scan noise or dagesh. Examples with ambiguous editorial stress
symbols were excluded before inference; this run does not test cantillation.
The Hebrew reference deliberately retains the visibly unpointed divine name.

| Script | Complete candidates | Exact matches | NFD comparison |
| --- | --- | --- | --- |
| Hebrew | 2/2 | 0/2 | 7 edits / 53 reference codepoints (13.21% CER) |
| Aramaic | 1/2 | 0/1 returned | 1 edit / 28 codepoints against a provisional reference; other response rejected |
| Greek | 1/2 | 1/1 returned | 0 edits / 34 codepoints; other response rejected |

The Hebrew candidates substituted holam with qamats and qubuts with segol; one
also changed consonants in a personal name. The provisional Aramaic comparison
substituted sheva with hataf patah. The longer Aramaic and Greek requests returned
`incomplete_response` and were rejected, not cached as successful candidates or
silently accepted as exact matches. Failed lines have no CER; they remain visible
in the completion denominator. Of the five image-verified references, only three
received complete candidates and one matched exactly. Their 7/87 combined
codepoint edits describe those three returned candidates only.

The run made exactly six inference requests and three read-only eligibility
checks, without retries. Four complete responses reported 4,538 prompt and 3,991
completion tokens (8,529 total). At the previously verified $0.75/M input and
$3.75/M output rates, these four responses alone have a $0.01836975 list-price
estimate. Usage for the two rejected responses is unavailable in the current
adapter, so total spend is unknown. Several successful responses reported nearly
1,024 completion tokens despite short visible transcriptions. This suggests an
output/reasoning-budget investigation, but the rejected responses' finish reasons
were not retained, so truncation is not established from these reports.

All four successful cache entries replayed with credentials removed, network
callbacks forbidden, zero inference requests and zero preflight requests.
Failed entries were excluded from replay to avoid unauthorized retry spend.
The offline dark viewer shows source images, frozen references, candidates,
source coordinates and mark differences, including explicit rejected responses.
Private artifacts are in `target/pdf-benchmark/line-benchmark/`: per-script
manifests/reports, `reference-review.json`, `summary.json`, and `index.html`.

This run does not justify automatic acceptance of historical-script extraction.
Keep the existing review-required policy and Gemini default unchanged; the earlier
two-word success did not generalize. The next bounded implementation step is to
retain safe finish-reason/usage metadata on rejected responses, then evaluate an
explicit reasoning/output budget before buying another accuracy run. Do not
silently increase the cap or change references to match generated text.

## Rejected-response accounting follow-up (2026-11-10)

The Gateway adapter now extracts allowlisted accounting before it validates a
candidate. A rejected JSON response can retain its known finish reason, prompt,
completion and total token counters, plus reasoning/cached-token detail counters.
Unknown reasons become `unknown`; missing or malformed counters stay absent.
Rejected content, reasoning text and provider messages are not serialized.
`recognition_failed`, null candidate text, request-budget consumption and absence
of successful cache entries remain unchanged. HTTP/transport errors without
usable accounting cannot supply a cost. The six-line benchmark's discarded data
has not been reconstructed or overwritten.

Credential-free tests cover truncation accounting through the complete pipeline,
safe handling of arbitrary finish reasons and malformed counters, malformed or
refused responses, unchanged retry behavior and successful-response metadata.
The suite has 25 tests; all passed, along with Ruff, strict mypy against the
Pillow-equipped OCR environment, `make fmt`, `make ci` and `git diff --check`.
This follow-up made no paid OCR requests.

Read-only inspection of the public model catalog confirmed that Gemini 3.6 Flash
supports reasoning effort `low` or `high`, not `minimal`; the documented Gateway
raw JSON extension is `reasoning.effort`. Request defaults and cache identity are
unchanged. A separate, explicitly configured `low`-effort experiment is the next
candidate, not a proven accuracy or cost improvement. See the tool README for
the official API references and experiment boundaries.

## Explicit low-effort comparison (2026-11-10)

The CLI now accepts `--gateway-reasoning-effort low|high` for Vercel only. The
authenticated catalog must advertise the selected effort before inference;
unsupported/missing capability fails closed with no inference call. The request
includes `reasoning.effort`, and its hash isolates the cache from unspecified or
other effort settings. Omitting the flag preserves the prior request/cache
identity and injected callback signatures. The output cap remains 1,024 tokens.

A separately authorized run made exactly six Gemini 3.6 Flash requests at `low`
effort, plus three eligibility checks. Manifest hashes matched the frozen baseline
manifests, and every rendered crop hash was checked before upload. No reference
text was sent, changed or promoted; the ambiguous Aramaic reference stays
provisional. No failed request was retried.

| Crop | Unspecified effort | Explicit low effort |
| --- | --- | --- |
| Hebrew 18b | 6 NFD edits | 4 NFD edits; still incorrect |
| Hebrew 18 | 1 NFD edit | Rejected; finish reason `length` |
| Aramaic 1 | 1 edit against provisional reference | Same provisional difference |
| Aramaic 5 | Rejected incomplete response | Exact match |
| Greek 1 | Exact match | Exact match |
| Greek 2 | Rejected incomplete response | Exact match |

Completion improved from 4/6 to 5/6 in this single run. Exact matches among the
five image-verified references increased from 1/5 to 3/5, but a different Hebrew
line failed and the remaining Hebrew output still changed consonants/vowels.
These are descriptive paired results, not statistical evidence of superiority or
human acceptance. CER on returned candidates has a different denominator in each
run and must not conceal rejected responses.

The new accounting retained all six responses, including the rejected one:
6,806 prompt tokens, 4,483 completion tokens, 11,289 total. Of the completion
tokens, 4,292 were reported as reasoning tokens; they are a subset, not an
additional charge. At the previously verified catalog rates, the full run's
list-price estimate is $0.02191575. The baseline's $0.01836975 covers only four
responses, so these figures do not establish overall savings. The rejected
Hebrew response reported `length`, 1,020 completion tokens and 980 reasoning
tokens: this new failure is confirmed truncation, unlike the old unrecorded
finish reasons. Low effort did not eliminate reasoning-budget pressure.

All five successful low-effort cache entries replayed with zero inference and
preflight requests, credentials removed and network callbacks forbidden. The
private dark viewer now shows default and low candidates alongside the unchanged
source/reference, including failure reasons and reasoning-token counts. Evidence
is in the existing private directory under `*-low-report.json`,
`*-low-timing.json`, `*-low-cached-successes.json` and `low-summary.json`.

Gemini remains review-required and unspecified effort remains the default. The
new flag is an experiment control, not an accuracy fix. Before another paid run,
select a bounded output-budget experiment or alternate recognizer rather than
automatically raising limits. Validation: 27 OCR tests, Ruff, strict mypy,
`make fmt`, `make ci` and `git diff --check` passed.

## One-crop 2,048-token experiment (2026-11-10)

After committing the explicit effort control, a separately authorized experiment
selected only `hebrew-line-18`, which had returned `length` at low effort and a
1,024-token cap. The runner changed `gateway_ocr.SETTINGS["max_tokens"]` to 2,048
only inside that Python process. Shipped defaults and source code were unchanged.
The request hash automatically isolated this configuration from the earlier
caches. Original manifest and rendered crop hashes were verified before upload;
the frozen reference, model, prompt and low effort were held fixed.

Exactly one inference request and one eligibility check were made, without retry.
The response completed with `finish_reason: stop`, but still replaced qubuts
(`U+05BB`) with segol (`U+05B6`) on bet: one NFD edit over 24 reference codepoints
(4.17% CER). The increased cap avoided truncation in this attempt; it did not
correct the vowel recognition error. A single attempt does not establish that
this cap will reliably avoid truncation on other inputs.

Usage was 1,143 prompt tokens and 1,850 completion tokens (2,993 total), of which
1,830 were reported as reasoning tokens. At the previously verified catalog
rates, the list-price estimate is $0.00779475. Reasoning tokens are included in
completion tokens. The candidate remains review-required and no source was
modified. A credential-free replay used the successful cache entry with zero
inference/preflight requests and callbacks that would fail on network access.

Private artifacts are `hebrew-low2048-{manifest,config,report}.json` and
`hebrew-low2048-cached-report.json` in the line benchmark directory. The dark
viewer includes the new result only for this one tested crop, beside default
and low-effort 1,024-token attempts. Increasing the global cap is not justified
as an accuracy fix; next investigate recognition quality rather than continuing
to buy more reasoning tokens for this crop.
