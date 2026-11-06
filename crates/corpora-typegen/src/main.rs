//! CLI: reads `schema/model.json` and writes generated types.
//!
//! ```text
//! corpora-typegen [--schema <path>] [--out <dir>]
//! ```
//!
//! Writes `types.rs`, `types.ts` and `schema.sql` under the output directory
//! (default `generated/`).

use std::path::PathBuf;

use anyhow::Context as _;
use corpora_typegen::{Schema, rust, sql, typescript};

fn main() -> anyhow::Result<()> {
    let mut schema_path = PathBuf::from("crates/corpora-core/schema/model.json");
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

    let json = std::fs::read_to_string(&schema_path)
        .with_context(|| format!("reading {}", schema_path.display()))?;
    let schema = Schema::from_json(&json).context("validating schema")?;

    std::fs::create_dir_all(&out_dir).with_context(|| format!("creating {}", out_dir.display()))?;

    for (name, content) in [
        ("types.rs", rust::emit(&schema)),
        ("types.ts", typescript::emit(&schema)),
        ("schema.sql", sql::emit(&schema)),
    ] {
        let path = out_dir.join(name);
        std::fs::write(&path, content).with_context(|| format!("writing {}", path.display()))?;
        println!("wrote {}", path.display());
    }
    Ok(())
}
