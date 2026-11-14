//! CLI: reads the schema directory and generates or checks types.
//!
//! ```text
//! corpora-typegen [--schema <dir-or-file>] [--out <dir>] [--check]
//! ```
//!
//! Manages `rust/`, `typescript/`, `swift/` and `sql/` under the output
//! directory (default `generated/`). Check mode compares bytes without writing.

use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

use anyhow::Context as _;
use corpora_typegen::{Schema, rust, sql, swift, typescript};

const HELP: &str = "Usage: corpora-typegen [--schema DIR_OR_FILE] [--out DIR] [--check]

  --schema DIR_OR_FILE  Schema directory or combined JSON file (default: crates/corpora-core/schema)
  --out DIR             Output directory (default: generated)
  --check               Check for missing, changed or extra files; never write
  -h, --help            Show this help

Generation overwrites expected files but never deletes extras.
Check mode manages all files under rust/, typescript/, swift/ and sql/;
other output paths are ignored. Review/remove extra files manually.";

fn main() -> anyhow::Result<()> {
    let mut schema_path = PathBuf::from("crates/corpora-core/schema");
    let mut out_dir = PathBuf::from("generated");
    let mut check = false;

    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--schema" => {
                schema_path = args.next().context("--schema needs a path")?.into();
            }
            "--out" => {
                out_dir = args.next().context("--out needs a directory")?.into();
            }
            "--check" => check = true,
            "-h" | "--help" => {
                println!("{HELP}");
                return Ok(());
            }
            other => anyhow::bail!("unknown argument `{other}`; use --help for usage"),
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

    let outputs = render_outputs(&schema);
    if check {
        check_outputs(&outputs, &out_dir).with_context(|| {
            format!(
                "generated-type freshness check failed. Regenerate with:\n  \
                 cargo run --locked -p corpora-typegen -- --schema {} --out {}\n\
                 Review/remove extra files manually; generation never deletes files",
                shell_quote(&schema_path),
                shell_quote(&out_dir)
            )
        })?;
        println!("{} generated files are up to date", outputs.len());
    } else {
        for (relative_path, content) in outputs {
            let path = out_dir.join(relative_path);
            if let Some(parent) = path.parent() {
                std::fs::create_dir_all(parent)
                    .with_context(|| format!("creating {}", parent.display()))?;
            }
            std::fs::write(&path, content)
                .with_context(|| format!("writing {}", path.display()))?;
            println!("wrote {}", path.display());
        }
    }
    Ok(())
}

fn render_outputs(schema: &Schema) -> BTreeMap<PathBuf, String> {
    let mut outputs = BTreeMap::new();
    for (language, files) in [
        ("rust", rust::emit(schema)),
        ("typescript", typescript::emit(schema)),
        ("swift", swift::emit(schema)),
    ] {
        for (name, content) in files {
            outputs.insert(Path::new(language).join(name), content);
        }
    }
    outputs.insert(PathBuf::from("sql/schema.sql"), sql::emit(schema));
    // Match repository EOF hygiene so regeneration and whitespace hooks agree.
    for content in outputs.values_mut() {
        content.truncate(content.trim_end_matches('\n').len());
        content.push('\n');
    }
    outputs
}

fn shell_quote(path: &Path) -> String {
    format!("'{}'", path.display().to_string().replace('\'', "'\\''"))
}

fn check_outputs(outputs: &BTreeMap<PathBuf, String>, out_dir: &Path) -> anyhow::Result<()> {
    let mut existing = BTreeMap::new();
    for language in ["rust", "typescript", "swift", "sql"] {
        collect_files(out_dir, Path::new(language), &mut existing)?;
    }

    let paths: BTreeSet<_> = outputs.keys().chain(existing.keys()).collect();
    let mut drift = Vec::new();
    for relative_path in paths {
        let path = out_dir.join(relative_path);
        let status = match (outputs.get(relative_path), existing.get(relative_path)) {
            (Some(_), None) => "missing",
            (None, Some(_)) => "extra",
            (Some(content), Some(is_file)) => {
                if *is_file {
                    let actual = std::fs::read(&path)
                        .with_context(|| format!("reading {}", path.display()))?;
                    if actual == content.as_bytes() {
                        continue;
                    }
                }
                "changed"
            }
            (None, None) => unreachable!("path is in the expected or existing inventory"),
        };
        drift.push(format!("  {status}: {}", path.display()));
    }
    anyhow::ensure!(
        drift.is_empty(),
        "generated outputs are stale:\n{}",
        drift.join("\n")
    );
    Ok(())
}

// Keep the inventory ordered and never follow symlinks into unrelated trees.
// The bool distinguishes regular files from symlinks or other non-file entries.
fn collect_files(
    out_dir: &Path,
    relative_path: &Path,
    files: &mut BTreeMap<PathBuf, bool>,
) -> anyhow::Result<()> {
    let path = out_dir.join(relative_path);
    let metadata = match std::fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(()),
        Err(error) => return Err(error).with_context(|| format!("inspecting {}", path.display())),
    };
    if metadata.is_dir() {
        for entry in
            std::fs::read_dir(&path).with_context(|| format!("listing {}", path.display()))?
        {
            let entry = entry.with_context(|| format!("listing {}", path.display()))?;
            collect_files(out_dir, &relative_path.join(entry.file_name()), files)?;
        }
    } else {
        files.insert(relative_path.to_owned(), metadata.is_file());
    }
    Ok(())
}
