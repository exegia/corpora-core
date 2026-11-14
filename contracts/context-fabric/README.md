# Context Fabric v1 graph contract

The JSON Schemas in `v1/` are copied from `exegia/corpora-py` commit
`377a01c265ad60f211a6e53dfc6020e983c976bc`, path
`packages/common/src/common/schemas/context_fabric/v1/`. Keep their wire
keys and validation rules aligned with the legacy ingestion service while
route ownership moves to `corpora-api`.

`crates/corpora-core/schema/domains/ingest.json` defines the shared graph
envelope and exact legacy JSON keys. `corpora-typegen` emits matching Rust,
TypeScript, Swift, and Python values and packages these entity schemas with
Python. The Python `validate_graph` function checks each entity against them.
