//! Black-box coverage of generation and the read-only freshness contract.

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::SystemTime;

use corpora_typegen::{Schema, python, rust, sql, swift, typescript};

static NEXT_ID: AtomicUsize = AtomicUsize::new(0);

struct Fixture {
    root: PathBuf,
}

impl Fixture {
    fn new() -> Self {
        // Keep even test scratch writes inside the requested crate scope.
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join(format!(
            ".typegen-test-{}-{}",
            std::process::id(),
            NEXT_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir(&root).unwrap();
        Self { root }
    }

    fn out(&self) -> PathBuf {
        self.root.join("output with spaces")
    }

    fn run(&self, args: &[&str]) -> Output {
        self.run_schema(&schema_dir(), args)
    }

    fn run_schema(&self, schema: &Path, args: &[&str]) -> Output {
        Command::new(env!("CARGO_BIN_EXE_corpora-typegen"))
            .arg("--schema")
            .arg(schema)
            .arg("--out")
            .arg(self.out())
            .args(args)
            .output()
            .unwrap()
    }

    fn generate(&self) {
        assert_success(&self.run(&[]));
    }
}

impl Drop for Fixture {
    fn drop(&mut self) {
        fs::remove_dir_all(&self.root).unwrap();
    }
}

fn schema_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../corpora-core/schema")
}

fn expected_outputs() -> BTreeMap<PathBuf, String> {
    let schema = Schema::from_dir(&schema_dir()).unwrap();
    let mut files = BTreeMap::new();
    for (target, outputs) in [
        ("rust", rust::emit(&schema)),
        ("typescript", typescript::emit(&schema)),
        ("swift", swift::emit(&schema)),
    ] {
        for (name, content) in outputs {
            files.insert(Path::new(target).join(name), content);
        }
    }
    files.insert(PathBuf::from("sql/schema.sql"), sql::emit(&schema));
    for (name, content) in python::emit(&schema).unwrap() {
        files.insert(Path::new("python").join(name), content);
    }
    files
        .into_iter()
        .map(|(path, content)| {
            let normalized = if content.is_empty() {
                content
            } else {
                format!("{}\n", content.trim_end_matches('\n'))
            };
            (path, normalized)
        })
        .collect()
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "stdout: {}\nstderr: {}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
}

fn assert_drift(output: &Output, status: &str, path: &Path) {
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(
        stderr.contains(&format!("{status}: {}", path.display())),
        "{stderr}"
    );
    assert!(stderr.contains("cargo run --locked -p corpora-typegen -- --schema"));
    assert!(stderr.contains("--out"));
    assert!(stderr.contains("generation never deletes files"));
    assert_eq!(output.stdout, [] as [u8; 0]);
}

fn snapshot(dir: &Path) -> BTreeMap<PathBuf, (SystemTime, Vec<u8>)> {
    let mut files = BTreeMap::new();
    for entry in fs::read_dir(dir).unwrap() {
        let entry = entry.unwrap();
        if entry.file_type().unwrap().is_dir() {
            files.extend(snapshot(&entry.path()));
        } else {
            files.insert(
                entry.path(),
                (
                    entry.metadata().unwrap().modified().unwrap(),
                    fs::read(entry.path()).unwrap(),
                ),
            );
        }
    }
    files
}

#[test]
fn generation_should_match_all_emitters_and_include_every_target_domain() {
    let fixture = Fixture::new();
    fixture.generate();
    let expected = expected_outputs();
    assert_eq!(snapshot(&fixture.out()).len(), expected.len());
    for (path, content) in &expected {
        assert_eq!(
            fs::read(fixture.out().join(path)).unwrap(),
            content.as_bytes()
        );
    }

    for domain in ["conversion", "document", "explore", "license", "platform"] {
        assert!(expected.contains_key(&Path::new("rust").join(format!("{domain}.rs"))));
        assert!(expected.contains_key(&Path::new("typescript").join(format!("{domain}.ts"))));
        let swift_name = format!(
            "{}{rest}.swift",
            domain[..1].to_uppercase(),
            rest = &domain[1..]
        );
        assert!(expected.contains_key(&Path::new("swift").join(swift_name)));
    }
    assert!(expected[Path::new("sql/schema.sql")].contains("CREATE TABLE"));
    assert!(
        expected[Path::new("python/src/corpora_schema_types/document.py")]
            .contains("class TextRange(BaseModel):")
    );

    let before = snapshot(&fixture.out());
    let checked = fixture.run(&["--check"]);
    assert_success(&checked);
    assert!(String::from_utf8_lossy(&checked.stdout).contains("generated files are up to date"));
    assert_eq!(snapshot(&fixture.out()), before);

    fixture.generate();
    for (path, (_, bytes)) in before {
        assert_eq!(fs::read(path).unwrap(), bytes);
    }
}

#[test]
fn check_should_report_each_missing_output_without_restoring_it() {
    let fixture = Fixture::new();
    fixture.generate();
    for (relative, content) in expected_outputs() {
        let path = fixture.out().join(relative);
        fs::remove_file(&path).unwrap();
        let before = snapshot(&fixture.out());
        assert_drift(&fixture.run(&["--check"]), "missing", &path);
        assert!(!path.exists());
        assert_eq!(snapshot(&fixture.out()), before);
        fs::write(path, content).unwrap();
    }
}

#[test]
fn check_should_report_each_changed_output_without_rewriting_it() {
    let fixture = Fixture::new();
    fixture.generate();
    for (relative, content) in expected_outputs() {
        let path = fixture.out().join(relative);
        // Invalid UTF-8 also counts as byte drift, not a text decoding error.
        fs::write(&path, [0xff, 0x00]).unwrap();
        let before = snapshot(&fixture.out());
        assert_drift(&fixture.run(&["--check"]), "changed", &path);
        assert_eq!(snapshot(&fixture.out()), before);
        fs::write(path, content).unwrap();
    }
}

#[test]
fn check_should_reject_line_ending_and_trailing_newline_drift() {
    let fixture = Fixture::new();
    fixture.generate();
    let path = fixture.out().join("typescript/enums.ts");
    let canonical = fs::read_to_string(&path).unwrap();
    assert!(canonical.ends_with('\n'));
    assert!(!canonical.ends_with("\n\n"));
    for changed in [canonical.replace('\n', "\r\n"), format!("{canonical}\n")] {
        fs::write(&path, changed).unwrap();
        let before = snapshot(&fixture.out());
        assert_drift(&fixture.run(&["--check"]), "changed", &path);
        assert_eq!(snapshot(&fixture.out()), before);
    }
}

#[test]
fn check_should_report_extra_files_in_every_target_without_deleting_them() {
    let fixture = Fixture::new();
    fixture.generate();
    for relative in [
        "rust/retired.rs",
        "typescript/retired.ts",
        "swift/Retired.swift",
        "sql/retired.sql",
        "python/src/corpora_schema_types/retired.py",
        "rust/nested/retired.rs",
        "typescript/notes.txt",
    ] {
        let path = fixture.out().join(relative);
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(&path, "user content, not necessarily generated").unwrap();
        let before = snapshot(&fixture.out());
        assert_drift(&fixture.run(&["--check"]), "extra", &path);
        assert_eq!(snapshot(&fixture.out()), before);
        fixture.generate();
        assert_eq!(
            fs::read_to_string(&path).unwrap(),
            "user content, not necessarily generated"
        );
        fs::remove_file(path).unwrap();
    }
    assert_success(&fixture.run(&["--check"]));
}

#[test]
fn check_ignores_python_bytecode_cache() {
    let fixture = Fixture::new();
    fixture.generate();
    let cache = fixture
        .out()
        .join("python/src/corpora_schema_types/__pycache__");
    fs::create_dir_all(&cache).unwrap();
    fs::write(cache.join("document.cpython-313.pyc"), b"bytecode").unwrap();
    assert_success(&fixture.run(&["--check"]));
}

#[test]
fn check_should_report_all_drift_in_stable_path_order() {
    let fixture = Fixture::new();
    fixture.generate();
    fs::remove_file(fixture.out().join("swift/Enums.swift")).unwrap();
    fs::write(fixture.out().join("rust/enums.rs"), "changed").unwrap();
    // Intentionally create extra paths in reverse lexical order.
    fs::write(fixture.out().join("typescript/z.ts"), "extra").unwrap();
    fs::write(fixture.out().join("typescript/a.ts"), "extra").unwrap();
    let before = snapshot(&fixture.out());
    let first = fixture.run(&["--check"]);
    let second = fixture.run(&["--check"]);
    assert_eq!(first.status.code(), Some(1));
    assert_eq!(first.stderr, second.stderr);
    let stderr = String::from_utf8_lossy(&first.stderr);
    let reported: Vec<_> = stderr
        .lines()
        .filter(|line| {
            let line = line.trim();
            line.starts_with("missing:")
                || line.starts_with("changed:")
                || line.starts_with("extra:")
        })
        .map(str::trim)
        .collect();
    assert_eq!(
        reported,
        [
            format!("changed: {}", fixture.out().join("rust/enums.rs").display()),
            format!(
                "missing: {}",
                fixture.out().join("swift/Enums.swift").display()
            ),
            format!("extra: {}", fixture.out().join("typescript/a.ts").display()),
            format!("extra: {}", fixture.out().join("typescript/z.ts").display()),
        ]
    );
    assert_eq!(snapshot(&fixture.out()), before);
}

#[test]
fn check_should_not_create_a_missing_output_directory() {
    let fixture = Fixture::new();
    let output = fixture.run(&["--check"]);
    assert_eq!(output.status.code(), Some(1));
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert_eq!(
        stderr
            .lines()
            .filter(|line| line.trim().starts_with("missing:"))
            .count(),
        expected_outputs().len()
    );
    assert!(!fixture.out().exists());
}

#[test]
fn check_should_ignore_paths_outside_the_four_managed_targets() {
    let fixture = Fixture::new();
    fixture.generate();
    fs::write(fixture.out().join("README.md"), "user notes").unwrap();
    fs::create_dir(fixture.out().join("custom")).unwrap();
    fs::write(fixture.out().join("custom/keep.rs"), "user code").unwrap();
    let before = snapshot(&fixture.out());
    assert_success(&fixture.run(&["--check"]));
    assert_eq!(snapshot(&fixture.out()), before);
    fixture.generate();
    assert_eq!(
        fs::read_to_string(fixture.out().join("README.md")).unwrap(),
        "user notes"
    );
    assert_eq!(
        fs::read_to_string(fixture.out().join("custom/keep.rs")).unwrap(),
        "user code"
    );
}

#[test]
fn split_schema_should_match_combined_schema_regardless_of_domain_creation_order() {
    let fixture = Fixture::new();
    let split = fixture.root.join("schema");
    fs::create_dir_all(split.join("domains")).unwrap();
    fs::write(split.join("model.json"), r#"{"version":"test"}"#).unwrap();
    let domain = r#"{"types":{"Thing":{"fields":{"name":{"type":"String"}}}}}"#;
    fs::write(split.join("domains/zeta.json"), domain).unwrap();
    fs::write(split.join("domains/alpha.json"), r#"{"types":{}}"#).unwrap();
    assert_success(&fixture.run_schema(&split, &[]));
    let before = snapshot(&fixture.out());
    let combined = fixture.root.join("combined.json");
    fs::write(
        &combined,
        format!(r#"{{"version":"test","domains":{{"zeta":{domain},"alpha":{{"types":{{}}}}}}}}"#),
    )
    .unwrap();
    assert_success(&fixture.run_schema(&combined, &["--check"]));
    assert_eq!(snapshot(&fixture.out()), before);
    assert_success(&fixture.run_schema(&combined, &[]));
    for (path, (_, bytes)) in before {
        assert_eq!(fs::read(path).unwrap(), bytes);
    }
}

#[test]
fn help_should_describe_check_without_loading_schema_or_writing() {
    let fixture = Fixture::new();
    let output = fixture.run_schema(&fixture.root.join("missing.json"), &["--help"]);
    assert_success(&output);
    assert!(String::from_utf8_lossy(&output.stdout).contains("--check"));
    assert!(!fixture.out().exists());
}

#[cfg(unix)]
#[test]
fn check_should_not_follow_symlinks_in_managed_targets() {
    use std::os::unix::fs::symlink;

    let fixture = Fixture::new();
    fixture.generate();
    let external = fixture.root.join("user.rs");
    let path = fixture.out().join("rust/enums.rs");
    fs::copy(&path, &external).unwrap();
    fs::remove_file(&path).unwrap();
    symlink(&external, &path).unwrap();
    assert_drift(&fixture.run(&["--check"]), "changed", &path);

    let link = fixture.out().join("typescript/linked");
    // A link back to the output tree must not cause recursive traversal.
    symlink(fixture.out(), &link).unwrap();
    assert_drift(&fixture.run(&["--check"]), "extra", &link);
    assert!(
        fs::symlink_metadata(&path)
            .unwrap()
            .file_type()
            .is_symlink()
    );
    assert!(
        fs::symlink_metadata(&link)
            .unwrap()
            .file_type()
            .is_symlink()
    );
}
