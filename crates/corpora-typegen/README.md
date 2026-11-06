# corpora-typegen

Generates Rust, TypeScript and SQL types from the Corpora schema definition
(`crates/corpora-core/schema/model.json`).

```sh
cargo run -p corpora-typegen            # writes generated/{types.rs,types.ts,schema.sql}
cargo run -p corpora-typegen -- --schema path/to/model.json --out dir
```

See `crates/corpora-core/schema/README.md` for the schema format.

Part of [corpora-core](https://github.com/exegia/corpora-core).
