# corpora-typegen

Generates Rust, TypeScript and SQL types from the Corpora schema definition
(`crates/corpora-core/schema/`: `model.json` plus `domains/*.json`).

```sh
cargo run -p corpora-typegen            # writes generated/{rust,typescript,sql}/
cargo run -p corpora-typegen -- --schema path/to/schema-dir --out dir
```

See `crates/corpora-core/schema/README.md` for the schema format.

Part of [corpora-core](https://github.com/exegia/corpora-core).
