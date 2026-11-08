//! The additive structural operation must not change legacy detection requests.
#![cfg(feature = "spellcheck")]

use std::{
    io::Write,
    process::{Command, Stdio},
};

#[test]
fn structural_operation_bypasses_dictionary_loading_and_preserves_legacy_detection() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_corpora-text-check"))
        .arg("/nonexistent/dictionaries")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let requests = [
        serde_json::json!({"operation":"structure", "source_id":"doc.xml", "text":"<a></A>"}),
        serde_json::json!({"text":"hello world", "locale":"en-US", "detect_only":true}),
        serde_json::json!({"operation":"unknown", "text":"<a/>"}),
    ];
    let mut stdin = child.stdin.take().unwrap();
    for request in requests {
        writeln!(stdin, "{request}").unwrap();
    }
    drop(stdin);
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let rows: Vec<serde_json::Value> = String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|line| serde_json::from_str(line).unwrap())
        .collect();
    assert_eq!(rows[0]["schema_version"], 1);
    assert_eq!(rows[0]["source_id"], "doc.xml");
    assert_eq!(rows[0]["diagnostics"][0]["code"], "xml_tag_case");
    assert_eq!(rows[1]["dictionary"], "en_US");
    assert!(rows[1].get("schema_version").is_none());
    assert!(rows[2].get("error").is_some());
}
