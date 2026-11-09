# Hosted quality review through Vercel AI SDK

This optional Node 22+ bridge gives the Python TEI converter structured correction
proposals using `generateText` and `Output.object`. The provider receives a portable JSON
shape; strict bounds and nonempty-value checks run locally on the returned object.
This avoids provider-specific schema constraint failures without relaxing validation. It needs no hosted web application
or Vercel deployment. Corpus text is sent to the selected Gateway model; credentials
stay in the process environment and never enter browser assets or quality receipts.

```sh
npm ci --prefix packages/quality-ai
npm run check --prefix packages/quality-ai
npm test --prefix packages/quality-ai
```

Create a Gateway API key and provide `AI_GATEWAY_API_KEY` through your secret manager
or local shell environment. Do not commit it or paste it into chat. The bridge does
not automatically load `.env` files. Run the converter with:

```sh
uv run --project packages/tei-to-tf tei-to-tf /path/to/tei \
  --output /new/quality-output \
  --quality-engine target/debug/corpora-text-check \
  --dictionaries target/cspell-dictionaries \
  --ai-bridge packages/quality-ai/bridge.mjs \
  --ai-model google/gemini-3.5-flash-lite \
  --ai-max-requests 100 --repair-cycles 3
```

As checked on 2026-11-06, [Gateway pricing](https://vercel.com/docs/ai-gateway/pricing)
offers $5 monthly free credits. The [model catalog](https://ai-gateway.vercel.sh/v1/models)
lists Gemini 3.5 Flash Lite with structured output at $0.30/million input tokens and
$2.50/million output tokens. Pricing/availability can change; a free credit balance is
not an unlimited free service. Set a provider budget and disable automatic top-ups if
you require zero spend. There is no automatic fallback to another model.

Limits: 100 requests per run by default, 100 findings per request, 100,000 context
characters, 4,096 output tokens, 60 seconds per model call, zero SDK retries. Identical
successful requests are cached in memory. The request cap is not a dollar budget.
Model and diagnostic status are recorded; API errors are sanitized. Missing credentials,
invalid output, exhausted budgets and unresolved red findings never imply approval.

The model has no tools and cannot write files. Its exact-span proposals pass local
guards: no corpus rewrites, no XML deletion, no cross-markup spelling replacement.
Red corrections must pass dictionary checks, and the complete candidate is reparsed
and revalidated before export. Orange suggestions are displayed without modifying text;
yellow findings do not need AI review. Ambiguous XML/schema or editorial choices may
remain blocked after the bounded repair loop. This is not a guarantee that arbitrary
broken TEI can be reconstructed correctly.

Offline SDK tests use the SDK's mock language model. A live model evaluation still
requires configured credentials and should be reported separately from mocked tests.
