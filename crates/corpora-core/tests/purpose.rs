//! Purpose validation is usable without dictionaries or Python.
use corpora_core::{
    diagnostic::SourceRange,
    purpose::{FieldPurpose, FieldStatus, validate_tei_metadata},
};

fn xml(fields: &str) -> String {
    format!(
        "<TEI xmlns='http://www.tei-c.org/ns/1.0'><teiHeader><fileDesc><publicationStmt>{fields}</publicationStmt></fileDesc></teiHeader><text><body><p>reading</p></body></text></TEI>"
    )
}

#[test]
fn supported_dates_pass_without_language_detection() {
    for value in [
        "2014",
        "1868-1873",
        "1868–1873",
        "2000-02-29",
        "2014-02",
        " 2014 ",
    ] {
        let text = xml(&format!("<date>{value}</date>"));
        let report = validate_tei_metadata("doc.xml", &text, None, false).unwrap();
        assert!(report.report.passed(), "{value}");
        assert_eq!(report.fields[0].status, FieldStatus::Validated);
        assert_eq!(report.fields[0].purpose, FieldPurpose::Date);
        assert_eq!(report.fields[0].value, value);
    }
    for fields in [
        "<date when='2014-02-20'/>",
        "<date from='1868' to='1873'>1868-1873</date>",
        "<date when='2000-02-29'>2000</date>",
    ] {
        assert!(
            validate_tei_metadata("doc.xml", &xml(fields), None, false)
                .unwrap()
                .report
                .passed()
        );
    }
}

#[test]
fn invalid_dates_and_conflicting_attributes_remain_blocked() {
    for fields in [
        "<date>1900-02-29</date>",
        "<date>2014-02-31</date>",
        "<date>0000</date>",
        "<date>1873-1868</date>",
        "<date>circa 1857</date>",
        "<date/>",
        "<date when='2015'>2014</date>",
        "<date when='2014-13'>2014</date>",
        "<date from='2015' to='2014'/>",
        "<date notBefore='2015' notAfter='2014'/>",
        "<date calendar='#unknown'>2014</date>",
        "<date>20<hi>14</hi></date>",
    ] {
        let text = xml(fields);
        let report = validate_tei_metadata("doc.xml", &text, None, false).unwrap();
        assert!(!report.report.passed(), "{fields}");
        assert_eq!(report.fields[0].status, FieldStatus::Blocked);
        let issue = &report.report.diagnostics[0];
        assert!(issue.blocking);
        assert_ne!(issue.locations.len(), 0);
        assert!(issue.suggestions.iter().all(|s| s.edits.is_empty()));
    }
}

#[test]
fn identifiers_use_explicit_caller_policy_and_never_suggest_rewrites() {
    let text = xml("<idno>doc-1</idno>");
    assert!(
        validate_tei_metadata("source", &text, Some("doc-1"), false)
            .unwrap()
            .report
            .passed()
    );
    for (value, expected) in [
        ("FDM-015-015-000-015", "FDM-016-016-000-017"),
        ("FDM-055-062-000-064-", "FDM-055-062-000-064"),
    ] {
        let text = xml(&format!("<idno>{value}</idno>"));
        let report = validate_tei_metadata("source", &text, Some(expected), false).unwrap();
        let issue = &report.report.diagnostics[0];
        assert_eq!(issue.code, "tei_identifier_mismatch");
        assert_eq!(
            &text[issue.locations[0].start.byte..issue.locations[0].end.byte],
            value
        );
        assert!(issue.suggestions.iter().all(|s| s.edits.is_empty()));
    }
    for fields in [
        "<idno type='ISBN'>9781234567890</idno>",
        "<idno subtype='local'>doc-1</idno>",
    ] {
        let report = validate_tei_metadata("source", &xml(fields), Some("doc-1"), false).unwrap();
        assert_eq!(
            report.report.diagnostics[0].code,
            "tei_identifier_policy_required"
        );
    }
    assert!(
        !validate_tei_metadata("source", &text, None, false)
            .unwrap()
            .report
            .passed()
    );
}

#[test]
fn reading_foreign_fields_and_collection_ids_are_not_misclassified() {
    let text = "<TEI xmlns='http://www.tei-c.org/ns/1.0' xmlns:x='urn:other'><teiHeader><x:date>wrong</x:date></teiHeader><text><body><date>circa 1857</date><idno>reading</idno></body></text></TEI>";
    assert_eq!(
        validate_tei_metadata("source", text, Some("source"), false)
            .unwrap()
            .fields
            .len(),
        0
    );
    let text = format!(
        "<teiCorpus xmlns='http://www.tei-c.org/ns/1.0'>{}</teiCorpus>",
        xml("<idno>doc-1</idno>")
    );
    let report = validate_tei_metadata("source", &text, Some("doc-1"), false).unwrap();
    assert_eq!(
        report.report.diagnostics[0].code,
        "tei_identifier_policy_required"
    );
    let no_namespace = xml("<date>2014</date>").replace(" xmlns='http://www.tei-c.org/ns/1.0'", "");
    assert_eq!(
        validate_tei_metadata("source", &no_namespace, None, false)
            .unwrap()
            .fields
            .len(),
        0
    );
    assert_eq!(
        validate_tei_metadata("source", &no_namespace, None, true)
            .unwrap()
            .fields
            .len(),
        1
    );
}

#[test]
fn unicode_entities_cdata_and_comments_keep_exact_raw_ranges() {
    let text = xml("😀\r\n<date><![CDATA[2014]]><!-- retained --></date><idno>doc&#45;2</idno>");
    let report = validate_tei_metadata("source", &text, Some("doc-1"), false).unwrap();
    assert_eq!(report.fields[0].value, "2014");
    assert_eq!(report.fields[0].status, FieldStatus::Validated);
    assert_eq!(report.fields[1].value, "doc-2");
    assert_eq!(report.fields[1].element_path, vec![0, 0, 0, 1]);
    let range = &report.report.diagnostics[0].locations[0];
    assert_eq!(&text[range.start.byte..range.end.byte], "doc&#45;2");
    assert!(range.start.byte > range.start.scalar);
    assert_eq!(range.start.line, 2);
    assert_eq!(
        *range,
        SourceRange::from_bytes(&text, range.start.byte..range.end.byte).unwrap()
    );
}
