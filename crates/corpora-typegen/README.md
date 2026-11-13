# corpora-typegen: one model, four languages

The [JSON schema](../corpora-core/schema/README.md) describes Corpora's shared
data shapes once. This crate turns it into matching Rust, TypeScript, Swift, and
SQL files. For example, a `Project` field in JSON can become a Rust field, a
TypeScript property, a Swift property, and a SQL column.

## Generate files

Run from the repository root:

```sh
cargo run --locked -p corpora-typegen
cargo run --locked -p corpora-typegen -- --schema crates/corpora-core/schema --out target/my-types
cargo run --locked -p corpora-typegen -- --check
```

| Parameter | Default | Purpose |
| --- | --- | --- |
| `--schema DIR_OR_FILE` | `crates/corpora-core/schema` | Read `model.json` plus `domains/*.json`, or one combined JSON file. |
| `--out DIR`            | `generated`                  | Generate or check `rust/`, `typescript/`, `swift/`, and `sql/schema.sql` below this directory. |
| `--check`              | Off                          | Compare expected outputs with disk without creating, updating or deleting anything.            |
| `-h`, `--help`         | —                            | Show usage without loading a schema or touching outputs.                                       |

Paths are relative to the current working directory. Generation prints each
written path in sorted order. It creates parent directories and overwrites
expected output files, but **never deletes extra files**. Edit the source schema,
then regenerate; do not fix generated files by hand. The schema README explains
`T?` (optional), `T[]` (list), `Map<K,V>` (map), table names and references.

## Freshness checking

`--check` uses exactly the same in-memory outputs as generation. Both modes
normalize emitter text to one final LF newline, matching repository EOF hygiene;
the library emitters themselves are unchanged. The check compares file bytes,
including whitespace and line endings, against that canonical output; it does
not normalize files on disk. No formatter or external language toolchain is
involved. Outputs and diagnostics have stable path order, with no timestamps or
dependence on directory enumeration order.

- Exit **0**: every expected file matches and there are no extra files. Prints
  the checked file count.
- Exit **1**: drift, invalid arguments/schema, or an I/O failure. Drift lists all
  **missing**, **changed** and **extra** paths, plus a regeneration command using
  the selected schema and output directory. A missing output directory reports
  missing files and is not created.
- All files recursively under `rust/`, `typescript/`, `swift/` and `sql/` are
  managed, including obsolete domain files and nested files. Any unexpected file
  there is reported as extra, even if it has no generated header. Empty
  directories are ignored. Keep unrelated user files outside these four trees;
  for example, an output-root `README.md` or `custom/` directory is ignored.
- Symlinks are not followed during inventory. A symlink at an expected file is
  changed, not fresh; unexpected symlinks are extra.

To repair drift, run generation without `--check`, then review and manually
remove or relocate reported extras before checking again. Generation preserves
extras, including non-generated user files; it does not decide what is safe to
delete.

For another destination or a combined schema file, use the same options in both
modes:

```sh
cargo run --locked -p corpora-typegen -- --schema model.json --out target/my-types
cargo run --locked -p corpora-typegen -- --schema model.json --out target/my-types --check
```

This contract checks `generated/` by default, not downstream packaging copies.
For example, `packages/corpora-types` receives `generated/typescript/*.ts` at
publish time; those copies are neither updated nor checked by the default
command. Run the default check before copying/package assembly. A future CI step
can run `cargo run --locked -p corpora-typegen -- --check` after the crate tests;
no root automation changes are required to use it locally.

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
cargo fmt -p corpora-typegen -- --check
cargo test --locked -p corpora-typegen
cargo run --locked -p corpora-typegen -- --check
```

The CLI tests cover all emitters and the conversion, document, explore, license
and platform domains; missing/changed outputs; extra and nested files in every
target; read-only behavior; stable diagnostics; split/combined schema parity;
and preservation of user files. Scratch outputs stay inside the crate and are
removed after each test.

License: MIT OR Apache-2.0.
