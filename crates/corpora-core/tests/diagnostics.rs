//! Public contract tests, including original-source Unicode coordinates and stale edits.

use corpora_core::diagnostic::{DiagnosticReport, SourceRange, TextEdit};

#[test]
fn ranges_retain_bytes_scalars_and_crlf_columns() {
    let text = "😀e\u{301}\r\n<&";
    let start = text.find('&').unwrap();
    let range = SourceRange::from_bytes(text, start..start + 1).unwrap();
    assert_eq!(
        (
            range.start.byte,
            range.start.scalar,
            range.start.line,
            range.start.column
        ),
        (10, 6, 2, 2)
    );
    assert_eq!(range.end.scalar, 7);
    assert!(SourceRange::from_bytes(text, 1..2).is_err());
    assert!(SourceRange::from_bytes(text, 99..100).is_err());
    let reversed = std::ops::Range { start: 4, end: 0 };
    assert!(SourceRange::from_bytes(text, reversed).is_err());
}

#[test]
fn edits_are_bound_to_the_whole_snapshot_and_exact_coordinates() {
    let text = "<a>😀 &</a>";
    let start = text.find('&').unwrap();
    let report = DiagnosticReport::new("source.xml", text, vec![]);
    let mut edit = TextEdit {
        range: SourceRange::from_bytes(text, start..start + 1).unwrap(),
        before: "&".into(),
        after: "&amp;".into(),
    };
    assert!(edit.matches_source(&report, text));
    assert!(!edit.matches_source(&report, "<a>😀 &</a> "));
    edit.before = "x".into();
    assert!(!edit.matches_source(&report, text));
    edit.before = "&".into();
    edit.range.start.scalar += 1;
    assert!(!edit.matches_source(&report, text));
    assert_eq!(report, DiagnosticReport::new("source.xml", text, vec![]));
}
