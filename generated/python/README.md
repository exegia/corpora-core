# Corpora schema types for Python

This package is generated from `crates/corpora-core/schema`. Install it from
this directory, or pin the `generated/python` subdirectory of a core commit.
Its package version follows the schema version. Run `make types` after editing
the schema and `make types-check` before committing.

The first reviewed value object is `TextRange`, serialized as
`{"start": 1, "end": 2}`. Its offsets count Unicode scalars. Both offsets
must fit `u32`; this schema does not currently assert `start <= end` or a
particular text length. Unknown input fields are ignored, matching Rust serde.
The separate `corpora-model` binding represents its
own `TextRange` as a JSON pair and checks ordering. Convert explicitly between
the two wire contracts rather than treating them as interchangeable.

`CanonicalGraph` uses the legacy `graph.json` keys (`schemaVersion`,
`sourceAsset`) and contains one work, edition, source asset, and ordered node
and fragment lists. `validate_graph` checks every entity against the pinned
Context Fabric v1 JSON Schemas packaged with this distribution. The envelope
comes from the shared `ingest` domain schema; HTTP job wrappers remain in
`corpora-api`.
