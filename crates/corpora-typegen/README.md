# corpora-typegen: one model, four languages

The [JSON schema](../corpora-core/schema/README.md) describes Corpora's shared
data shapes once. This crate turns it into matching Rust, TypeScript, Swift, and
SQL files. For example, a `Project` field in JSON can become a Rust field, a
TypeScript property, a Swift property, and a SQL column.

## Generate files

Run from the repository root:

```sh
cargo run -p corpora-typegen
cargo run -p corpora-typegen -- --schema crates/corpora-core/schema --out target/my-types
```

| Parameter | Default | Purpose |
| --- | --- | --- |
| `--schema DIR_OR_FILE` | `crates/corpora-core/schema` | Read `model.json` plus `domains/*.json`, or one combined JSON file. |
| `--out DIR` | `generated` | Write `rust/`, `typescript/`, `swift/`, and `sql/schema.sql` below this directory. |

The command writes the generated paths it created. Edit the source schema,
then regenerate; do not fix generated files by hand. The schema README explains
`T?` (optional), `T[]` (list), `Map<K,V>` (map), table names and references.

## Rust library API

```rust
use std::path::Path;
use corpora_typegen::{rust, sql, swift, typescript, Schema};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let schema = Schema::from_dir(Path::new("crates/corpora-core/schema"))?;
    let rust_files = rust::emit(&schema);
    let ts_files = typescript::emit(&schema);
    let swift_files = swift::emit(&schema);
    let sql_text = sql::emit(&schema);
    println!("{} Rust files, {} TS files, {} Swift files, {} SQL bytes",
        rust_files.len(), ts_files.len(), swift_files.len(), sql_text.len());
    Ok(())
}
```

| Method | Input → output | Why call it |
| --- | --- | --- |
| `Schema::from_dir(path)` | Schema directory → `Result<Schema, SchemaError>` | Load the normal split schema and check references. |
| `Schema::from_json(json)` | Combined JSON string → `Result<Schema, SchemaError>` | Load one in-memory schema. |
| `Schema::type_home(name)` | Type name → optional `TypeHome` | Find what kind of definition owns a name. |
| `Schema::find_type(name)` | Type name → optional `(name, TypeDef)` pair | Inspect a declared struct and its definition. |
| `TypeDef::fields()` | No parameters → field iterator | Read field names and definitions in declaration order. |
| `TableSpec::name()` | No parameters → optional table name | Tell a database table from a JSON value object. |
| `FieldType::parse(expr)` / `.named()` | `T?`, `T[]`, `Map<K,V>` text → parsed/named types | Understand field type expressions. |
| `rust::emit`, `typescript::emit`, `swift::emit` | `&Schema` → `(filename, content)` pairs | Generate language files without writing to disk. |
| `sql::emit` | `&Schema` → SQL string | Generate the database shape. |

`SchemaError` distinguishes file/JSON errors from unknown types and broken
foreign-key references. The library emitters return content; the CLI is the
part that writes it to disk. Generated SQL describes the current shape and
does not replace database migration planning.

## Check this crate

```sh
cargo test --locked -p corpora-typegen
cargo run -p corpora-typegen -- --out target/typegen-smoke
```

License: MIT OR Apache-2.0.
