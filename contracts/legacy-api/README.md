# Legacy REST migration contract

This directory pins the `corpora-py` OpenAPI document fetched from
`https://api.exegia.co/openapi.json` on 2026-11-13. `operations.json` maps every
in-scope method and path to its proposed `/v1` equivalent and migration ticket.
The checked snapshot has 77 operations: 63 mapped here and 14 under `/convert`
that stay with `corpora-py`. `/ingest` and the two `/linking` conversion-event
operations are deliberately included.

`GET /v1/health` already exists in `corpora-api` with the same `{"status":"ok"}`
response. It is marked `existing`; the other target routes are `proposed`.

Each inventory row points to the complete request, response, parameter, and
documented error shapes in `openapi.json` through `openapi_operation_pointer`.
`documented_response_statuses` and `documented_error_statuses` are copied from
that operation. `legacy_auth`, `state_dependencies`, and `source_module` record
the runtime boundary that OpenAPI does not describe. The legacy app's ASGI
middleware requires a Supabase JWT when `AUTH_REQUIRED` is enabled, except for
`/health` and `/capabilities`. Missing or invalid tokens return 401. AI chat
currently returns 501; drafts, threads, suggestions, and change history have
their own live storage and mutation paths. The linking router is conditionally
configured.

The status lists are a **documented contract**, not an exhaustive list of
runtime errors. For example, storage and ingestion source modules can also
return state or backing-service errors absent from OpenAPI. Each domain ticket
must compare those source paths and live error responses before switching route
ownership. `source_module` gives the review entrypoint for that work.

`python3 -m unittest tests.test_legacy_api_contract` checks the snapshot hash,
operation coverage, mappings, exclusions, and response-status references
offline. Update both JSON files together if the legacy contract changes.
