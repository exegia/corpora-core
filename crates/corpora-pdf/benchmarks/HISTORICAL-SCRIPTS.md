# Historical-script extraction investigation

Date: 2026-11-09. Status: researched recommendation; no new recognizer is accepted
or integrated by this document. Builds on the failed pointed-word smoke tests in
[VERIFICATION.md](VERIFICATION.md). Prices and upstream models must be rechecked
before a paid run or deployment.

## Recommended approach

Use local, script- and typography-specific recognition behind one source-preserving
adapter. Retain Poppler/Tesseract for material where they measure well; use Kraken
as the first specialist runtime, starting with a polytonic-Greek model. For Hebrew
and Hebrew-script Aramaic, evaluate pointed-text fine-tuning with explicitly covered
marks. Route unsupported material to review rather than silently discarding it.

This recommends an extensible workflow, **not the stock Kraken multilingual weights**:
those weights passed the vowel alphabet check but omitted both sampled vowels.
No examined source establishes one production-ready model for every requested
script, period, typography and image type.

For every script, inspect the embedded PDF text and character mapping first.
Preserve a source-faithful native extraction when available; send damaged mappings
or scanned regions through recognition. A text layer's existence or a high OCR
confidence score alone does not establish fidelity. Keep mixed native/OCR provenance
per region and check the rendered marks and reading order.

Why this route: it reuses our page geometry, provenance and benchmark machinery;
local inference has no per-page API charge; specialist models can learn the visible
marks; and reviewed corrections can become training examples. Annotation and
engineering time remain real costs. For small one-off jobs a hosted service may
cost less overall, if it passes the same visual fidelity tests.

## Evidence from similar failures

| Primary source | Finding | Consequence for our implementation |
| --- | --- | --- |
| [Tesseract #4119](https://github.com/tesseract-ocr/tesseract/issues/4119) | Report of pointed-Hebrew failure with default and best models; issue remains open when checked. | A `heb` language label is not a niqqud guarantee. Audit the actual codec and output. |
| [Tesseract #657](https://github.com/tesseract-ocr/tesseract/issues/657) | Diacritics can be separated into their own text lines. | Inspect line crops and preserve marks above/below the baseline before tuning recognition. |
| [Kraken #155](https://github.com/mittagessen/kraken/issues/155) | Historical report of line merging and boundaries mishandling diacritics. | Treat segmentation and recognition as separate tests; this report does not establish a current-version defect. |
| [Kraken #546](https://github.com/mittagessen/kraken/issues/546) | An old Syriac CLSTM model fails in a newer runtime. | Pin model format and compatible runtime; archive model hashes and run a load test. |
| [Ancient Greek visual-grounding study](https://arxiv.org/abs/2605.27750) | VLMs can produce fluent Greek substitutions unsupported by pixels. | Language-model fluency and dictionary agreement cannot certify an original reading. |

Our current evidence is narrower: two three-character words, assistant-transcribed
and not independently verified. It demonstrates missing vowels, not population
accuracy. Neither linguistic vowel restoration nor spellcheck should manufacture
marks that the source recognizer failed to read.

## Route by material, language and script

Interpret the requested “urugaic” as **Ugaritic**. Store language, script and
material separately: a language may use several scripts, and an edition may show
the original script beside Latin transliteration.

| Target | First route to evaluate | Boundary / required evidence |
| --- | --- | --- |
| Koine / polytonic Greek print | [CLLG Polytonic Greek model](https://zenodo.org/records/22232579), `ppocr_v6_tau090.safetensors`, CC BY 4.0, for Kraken; compare [Pogretra/commentary models](https://github.com/AjaxMultiCommentary/OCR-kraken-models), also CC BY 4.0. | CLLG targets historical polytonic editions, including Greek/Latin mixtures. Audit accents, breathings, diaeresis and iota subscript; test our typography. Printed editions do not establish papyrus/manuscript coverage. |
| Latin | Preserve a trustworthy native layer; compare Tesseract `lat` with the matching historical-print specialist. | Preserve macrons, abbreviations, ligatures and edition-specific spelling. Greek/Latin mixed lines need testing together, not automatic splitting at every script boundary. |
| Pointed Hebrew; Aramaic in Hebrew script | Fine-tune a small Kraken recognizer with corrected real lines and licensed synthetic examples; expand the codec where necessary. | Include niqqud, meteg, cantillation and editorial marks actually required by the corpus. The general multilingual model is only an initialization candidate, not an accepted recognizer. |
| Syriac / other Aramaic scripts | Evaluate Qoruyo [printed Serto](https://zenodo.org/records/17406677) or [Eastern Syriac](https://zenodo.org/records/17406690), both CC BY 4.0 verified through the primary API. [ETCBC syrocr](https://github.com/ETCBC/syrocr) is precedent for edition-specific supervised recognition. | Audit the printed models' actual codecs before assuming vowel coverage. The [Sophro Mhiro manuscript model](https://zenodo.org/records/17406773) explicitly excludes vowels in its training transcription policy, so reject it for vowel-preserving extraction. Hebrew-script support does not imply other Aramaic scripts. |
| Arabic | Compare a suitable local Arabic recognizer with a hosted baseline, retaining vowel marks and combining signs. | Modern Standard Arabic support does not establish historical/Quranic mark fidelity. Preserve dots and marks during binarization/cropping; test joining, logical order and mixed-script passages. |
| Ugaritic | For printed Unicode signs, investigate a dedicated codec and font-aware synthetic training plus real scans. Use the [Copenhagen Ugaritic corpus](https://github.com/DT-UCPH/cuc) as structured textual reference. | A textual corpus is not a photo recognizer. Ugaritic alphabetic cuneiform is not interchangeable with Akkadian/Sumerian sign recognition. |
| Phoenician / Punic | Separate printed alphabet recognition from inscription-photo detection; [DEAPS](https://dlato.osu.edu/blog/phoenician-and-punic-inscriptions-deaps) offers primary edition/image leads. | No ready general model was verified in this search. The [HPCDB character dataset](https://data.mendeley.com/datasets/x5prh2hyj8/1) is isolated handwriting, not ancient stone photographs; do not treat it as an end-to-end solution. |
| Akkadian / Sumerian and other Mesopotamian material | Investigate [eBL cuneiform-ocr](https://github.com/ElectronicBabylonianLiterature/cuneiform-ocr) for dedicated sign localization/classification; separate routes for printed signs and Latin transliteration. | Preserve visible sign identity, alternatives and damage; readings/transliteration/translation are later annotations. The [annotated-sign dataset](https://reference-global.com/article/10.5334/johd.503?tab=article) uses CC BY-NC 4.0 image crops; code/weight reuse rights need separate verification. This is not validated Ugaritic recognition. |

The CLLG record was checked through the Zenodo API, including its license and
actual file listing. Its safetensors header was inspected before any accuracy run:
all nine checked marks are present after NFD decomposition (grave U+0300,
acute U+0301, perispomeni U+0342, smooth/rough breathings U+0313/U+0314,
iota subscript U+0345, diaeresis U+0308, macron U+0304 and breve U+0306).
Header SHA-256: `9c6ee1d9be6a4a459fa5a6b1c2eaba1d57c23cd2bc18b77a668157fc5719bdf4`;
upstream full-file checksum: `md5:2b59c47ba44a58ca7200d6f0e51676dd` (not a locally
verified full-weight hash). Evidence is in ignored
`target/pdf-benchmark/models/cllg-greek-22232579/alphabet-audit.json`.
This is a preliminary mark-alphabet pass, not proof of recognition accuracy or
complete coverage of every edition's characters. No complete weight download or
paid recognition request was needed. A specialist's code license, weight license
and training-data/image rights are separate checks.

## Cost-friendly alternatives

| Option | Published or operational cost | Trade-off |
| --- | --- | --- |
| **Recommended: local specialists + bounded review fallback** | No metered inference fee; CPU/GPU, model adaptation and verified annotation time. [Kraken code](https://github.com/mittagessen/kraken/blob/main/LICENSE) is Apache 2.0; weight licenses vary. | Best control over exact marks, reproducibility and use of reviewed examples. Requires targeted training where models fail. |
| Google Cloud Vision Document Text Detection | [First 1,000 units/month free; then $1.50/1,000 units](https://cloud.google.com/vision/pricing) in the first paid tier. A PDF page is an image; each requested feature is a unit. | Cheap independent baseline. [Documented languages](https://docs.cloud.google.com/vision/docs/languages) include Greek, Hebrew and Arabic; this is not evidence of complete ancient-script or diacritic support. |
| Pinned Mistral OCR 3 (`mistral-ocr-2512`) | [Current model page: $2/1,000 pages](https://docs.mistral.ai/models/ocr-3-25-12); $3/1,000 annotated pages. A newer OCR model exists; do not use a moving `latest` alias for controlled evaluation. | Simple hosted full-page comparison; mark preservation and source coordinates still need measurement. A language claim is insufficient for Ugaritic, Phoenician or tablet photos. |

Example: 10,000 single-feature page units in one month cost $13.50 for Google
after its free allowance, or $20 for OCR 3 at the quoted standard rate, before
storage, tax, retries and review labor. Sending many crops counts as many images
and can negate a page-based cost comparison. These are arithmetic estimates, not
quotes for the user's account. No credentials were used or corpus text uploaded.

Cache by source/crop hash, rendering settings, model hash, decoder settings and
policy version. Revalidate changes locally; never rerun unchanged pages merely
because a reviewer changed another page. Escalate only unresolved regions, with
a cap on requests and a single bounded retry. Optimize total cost per accepted
page, including human correction time, rather than tokens alone.

## Experiment and acceptance plan

1. Build a small fixed, human-verified real-page set spanning the target scripts,
   typography and mixed-script layouts. Existing attachments cover only some
   groups. Keep training, validation and final test books separate; do not use a
   modern digital edition as ground truth without checking it against the image.
2. Audit each actual codec under canonical decomposition before inference. Record
   required/missing signs, base letters, vowels, cantillation and editorial marks.
   Fonts can supply training glyphs but cannot expand a pretrained model's alphabet.
3. Compare recognition on identical reviewed line crops first, then evaluate the
   complete page pipeline. Test image scale/crop margins without changing reference
   content; tiny dots must survive. Do not increase scale without checking actual
   native resolution or blindly denoise detached marks away.
4. Report ordinary CER/WER plus exact grapheme accuracy, mark precision/recall
   aligned to the correct base character, omissions, repetitions, logical order,
   crop coverage, runtime and review minutes. Preserve raw code points; use NFC/NFD
   equivalence for scoring, not accent stripping or compatibility folding. Track
   inserted as well as missing marks. Confidence scores need calibration.
5. Promote a route only on held-out source images, with its supported material
   explicitly declared. Unknown scripts produce an unsupported/review status and
   retained crop, never an empty successful transcription. Prioritize the Greek
   specialist alphabet audit and mark-aware scorer as the next bounded increment;
   pointed Hebrew adaptation follows reviewed training data.

[Kraken training](https://kraken.re/main/user_guide/training_recognition.html)
supports fine-tuning and extending the output codec with `--resize union`.
Use explicit evaluation manifests; a changing random split obscures comparisons.
A matching licensed font would help generate rare mark combinations, but synthetic
accuracy cannot substitute for held-out real scans. Training size and duration
must be measured with a learning curve rather than promised in advance.

## Proposed boundary for the later review API

The existing raw extraction is immutable evidence. The downstream API should
create versioned amendments and a derived reading, not overwrite source OCR.
This is a proposed contract, not an implemented endpoint:

| Record | Required information |
| --- | --- |
| Source anchor | Original file SHA-256, physical page index, crop polygon and coordinate space, raster dimensions, crop hash and segmentation revision. |
| Recognition evidence | Stable region ID; engine/version/model hash; language/script/material hints; raw text and code points; character or word geometry only where actually available; alternatives and uncalibrated confidence explicitly labeled. |
| Review finding | Missing/uncertain marks, script ambiguity, layout/ordering problem or unsupported region; links to source pixels and the exact extraction revision. |
| Amendment | Region ID, expected revision/text hash, original range in Unicode scalar coordinates, replacement, reason, reviewer identity/time and decision. Reject stale edits; retain audit history and idempotency keys. |
| Export | Raw reading and reviewed reading with provenance; source-to-derived span mappings after insertions/deletions; PAGE/ALTO where suitable, with normalized TF features later. |

An AI suggestion and a human-approved correction must have different states.
Keep literal signs, normalized text, transliteration and editorial reconstruction
as separate layers. Do not reverse RTL strings naively, detach combining marks,
guess undeciphered signs, or turn an illegible patch into a confident word.
