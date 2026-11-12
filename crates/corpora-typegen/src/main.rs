//! CLI: reads the schema directory and writes generated types.
//!
//! ```text
//! corpora-typegen [--schema <dir-or-file>] [--out <dir>]
//! ```
//!
//! Writes `rust/`, `typescript/` and `sql/schema.sql` under the output
//! directory (default `generated/`). The schema path may be a directory
//! containing `model.json` plus `domains/*.json`, or a single JSON file.

use std::path::PathBuf;

use anyhow::Context as _;
use corpora_typegen::{Schema, rust, sql, swift, typescript};

fn main() -> anyhow::Result<()> {
    let mut schema_path = PathBuf::from("crates/corpora-core/schema");
    let mut out_dir = PathBuf::from("generated");

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--schema" => {
                schema_path = args.next().context("--schema needs a path")?.into();
            }
            "--out" => {
                out_dir = args.next().context("--out needs a directory")?.into();
            }
            other => anyhow::bail!("unknown argument `{other}`"),
        }
    }

    let schema = if schema_path.is_dir() {
        Schema::from_dir(&schema_path)
    } else {
        let json = std::fs::read_to_string(&schema_path)
            .with_context(|| format!("reading {}", schema_path.display()))?;
        Schema::from_json(&json)
    }
    .context("loading schema")?;

    let mut outputs: Vec<(PathBuf, String)> = Vec::new();
    for (name, content) in rust::emit(&schema) {
        outputs.push((out_dir.join("rust").join(name), content));
    }
    for (name, content) in typescript::emit(&schema) {
        outputs.push((out_dir.join("typescript").join(name), content));
    }
    for (name, content) in swift::emit(&schema) {
        outputs.push((out_dir.join("swift").join(name), content));
    }
    outputs.push((out_dir.join("sql").join("schema.sql"), sql::emit(&schema)));

    for (path, content) in outputs {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent)
                .with_context(|| format!("creating {}", parent.display()))?;
        }
        std::fs::write(&path, content).with_context(|| format!("writing {}", path.display()))?;
        println!("wrote {}", path.display());
    }
    Ok(())
}
