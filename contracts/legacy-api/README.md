# Legacy REST migration contract

This directory pins the `corpora-py` OpenAPI document fetched from
`https://api.exegia.co/openapi.json` on 2026-11-13. Its source-code review is
pinned to `exegia/corpora-py` commit `d9c6e3d32b825eb7a5ac75114eaeb249821df2a2`.
`operations.json` maps every
in-scope method and path to its proposed `/v1` equivalent and migration ticket.
The checked snapshot has 77 operations: 63 mapped here and 14 under `/convert`
that stay with `corpora-py`. `/ingest` and the two `/linking` conversion-event
operations are deliberately included.

`GET /v1/health` already exists in `corpora-api` with the same `{"status":"ok"}`
response. It is marked `existing`; the other target routes are `proposed`.

| Domain | Proposed code owner | Stable type authority |
| --- | --- | --- |
| Platform | `corpora-api` | API response models |
| Ingestion and storage | `corpora-source` interfaces, Python workers and adapters in `corpora-api` | `corpora-core` schema for stable graph and archive types |
| Validation, corpus detail, and references | `corpora-fabric` | `corpora-core` schema for stable findings and references |
| Linking | New `corpora-linking` crate | `corpora-core` schema for stable ledger and selection types |
| AI curation | New `corpora-curation` crate, provider calls in `corpora-api` | `corpora-core` schema for stable draft and change types |

These are ownership proposals for the migration tickets. Ticket 02 must prove
how Python consumes generated types before committing to a binding mechanism.
The separate `corpora-model` Python binding has overlapping wire shapes that
need comparison before reuse. HTTP request and response wrappers stay in
`corpora-api`.

Each inventory row points to the complete request, response, parameter, and
documented error shapes in `openapi.json` through `openapi_operation_pointer`.
`documented_response_statuses` and `documented_error_statuses` are copied from
that operation. `legacy_auth`, `state_dependencies`, and `source_module` record
the runtime boundary that OpenAPI does not describe. The legacy app's ASGI
middleware requires a Supabase JWT when `AUTH_REQUIRED` is enabled, except for
`/health` and `/capabilities`. `route_identity_policy` records additional
handler checks: linking always requires a Bearer token; draft and mutation
routes require a verified owner; thread routes permit local SQLite identity
when global authentication is off. Missing or invalid tokens return 401. AI chat
currently returns 501; drafts, threads, suggestions, and change history have
their own live storage and mutation paths. The linking router is conditionally
configured.

Archive access depends on the selected backend: the default Hugging Face
storage is shared, while Supabase storage scopes by the verified owner.
`POST /validate` resolves `job_id` first, then a local server `path`, then a
loaded corpus; a hosted replacement must decide which modes it can safely
serve. Corpus restore currently returns 501 (or 403 in read-only deployments),
so implementing restore in ticket 09 is an explicit enhancement. AI apply,
undo, and change history return 501 while the mutation deployment flag is off.

`runtime_error_statuses` lists known source-code statuses absent from, or in
addition to, the OpenAPI declarations. It is a conservative review aid, not an
exhaustive promise for every backing configuration. Each domain ticket must
compare source paths and live error responses before switching route
ownership. `source_module` gives the review entrypoint for that work.

`python3 -m unittest tests.test_legacy_api_contract` checks the snapshot hash,
operation coverage, mappings, exclusions, and response-status references
offline. Update both JSON files together if the legacy contract changes.
