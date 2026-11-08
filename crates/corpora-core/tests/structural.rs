//! Native XML checks require neither Python nor the spellcheck feature.

use corpora_core::{
    diagnostic::Applicability,
    structural::{StructuralOptions, check_xml, check_xml_with_options},
};

#[test]
fn exact_case_edit_targets_only_the_failing_occurrence_after_unicode() {
    let text = "<r>😀e\u{301}\r\n<x></x><x></X></r>";
    let report = check_xml("source.xml", text).unwrap();
    assert!(!report.passed());
    let issue = &report.diagnostics[0];
    assert_eq!(issue.code, "xml_tag_case");
    let suggestion = &issue.suggestions[0];
    assert_eq!(suggestion.applicability, Applicability::Automatic);
    let edit = &suggestion.edits[0];
    assert!(edit.matches_source(&report, text));
    assert_eq!(edit.range.start.byte, text.find("</X>").unwrap());
    assert_eq!((edit.range.start.line, edit.range.start.column), (2, 11));
    let candidate = format!(
        "{}{}{}",
        &text[..edit.range.start.byte],
        edit.after,
        &text[edit.range.end.byte..]
    );
    assert!(check_xml("source.xml", &candidate).unwrap().passed());
    assert!(!report.matches_source(&candidate));
}

#[test]
fn ampersands_in_protected_content_and_valid_entities_are_not_flagged() {
    let text = "<?test &?><r><!-- & --><![CDATA[&]]>&amp; &#38; &#x26;</r>";
    assert!(check_xml("source.xml", text).unwrap().passed());
    let text = "<r>😀 & value</r>";
    let report = check_xml("source.xml", text).unwrap();
    let issue = &report.diagnostics[0];
    assert_eq!(issue.code, "xml_bare_ampersand");
    let edit = &issue.suggestions[0].edits[0];
    assert!(edit.matches_source(&report, text));
    assert_eq!(edit.range.start.byte, text.find('&').unwrap());
    assert_eq!(edit.after, "&amp;");
}

#[test]
fn unknown_entities_and_ambiguous_tag_mismatches_have_no_invented_edits() {
    for text in ["<r>&unknown;</r>", "<r><a></b></r>"] {
        let report = check_xml("source.xml", text).unwrap();
        assert!(!report.passed());
        assert!(
            report
                .diagnostics
                .iter()
                .flat_map(|d| &d.suggestions)
                .all(|s| s.edits.is_empty())
        );
    }
}

#[test]
fn truncation_dtd_and_resource_limits_do_not_fabricate_locations() {
    for text in [
        "",
        "<r>",
        "<r",
        "<!DOCTYPE r SYSTEM 'https://invalid.example/dtd'><r/>",
    ] {
        let report = check_xml("source.xml", text).unwrap();
        assert!(!report.passed());
        assert_eq!(report.diagnostics[0].locations.len(), 0);
    }
    for options in [
        StructuralOptions {
            max_bytes: 2,
            ..Default::default()
        },
        StructuralOptions {
            max_nodes: 1,
            ..Default::default()
        },
    ] {
        let report = check_xml_with_options("source.xml", "<r><a/></r>", options).unwrap();
        assert!(!report.passed());
        assert_eq!(report.diagnostics[0].locations.len(), 0);
    }
}

#[test]
fn namespace_and_duplicate_attribute_errors_are_blocking() {
    for text in [
        "<x:r/>",
        "<r xmlns:a='urn:x' xmlns:b='urn:x' a:v='1' b:v='2'/>",
    ] {
        assert!(!check_xml("source.xml", text).unwrap().passed());
    }
}

#[test]
fn tei_profile_reports_duplicate_id_ranges_and_adapter_boundaries() {
    let text = "<TEI xmlns='http://www.tei-c.org/ns/1.0'><text xml:id='a'/><text xml:id='a'/><standOff><span/></standOff></TEI>";
    let options = StructuralOptions {
        tei: true,
        ..Default::default()
    };
    let report = check_xml_with_options("tei.xml", text, options).unwrap();
    assert_eq!(report.diagnostics.len(), 2);
    let duplicate = &report.diagnostics[0];
    assert_eq!(duplicate.code, "tei_duplicate_id");
    assert_eq!(duplicate.locations.len(), 2);
    for range in &duplicate.locations {
        assert_eq!(&text[range.start.byte..range.end.byte], "xml:id='a'");
    }
    assert_eq!(report.diagnostics[1].code, "tei_adapter_required");
    assert!(
        !check_xml_with_options("tei.xml", "<TEI><text/></TEI>", options)
            .unwrap()
            .passed()
    );
    assert!(
        check_xml_with_options(
            "tei.xml",
            "<TEI><text/></TEI>",
            StructuralOptions {
                allow_no_namespace: true,
                ..options
            }
        )
        .unwrap()
        .passed()
    );
    // XML-only checking does not impose a TEI profile on another document format.
    assert!(check_xml("other.xml", "<root/>").unwrap().passed());
}
