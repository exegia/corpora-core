//! Native, bounded XML diagnostics; no recovery, network access, or source mutation.
//!
//! This is XML well-formedness plus optional TEI adapter-boundary checks, not TEI P5
//! schema validation, editorial reading selection, or a document conversion engine.

use crate::{
    Result,
    diagnostic::{
        Applicability, Certainty, Diagnostic, DiagnosticCategory, DiagnosticReport, Severity,
        SourceMap, SourceRange, Suggestion, TextEdit,
    },
};
use std::collections::HashMap;

const TEI: &str = "http://www.tei-c.org/ns/1.0";
const XML: &str = "http://www.w3.org/XML/1998/namespace";

/// Resource bounds and optional TEI checks.
#[derive(Debug, Clone, Copy)]
pub struct StructuralOptions {
    /// Maximum UTF-8 input size; default 64 MiB.
    pub max_bytes: usize,
    /// Parser node budget; default one million.
    pub max_nodes: u32,
    /// Check TEI identity, namespace, duplicate IDs and unsupported adapter constructs.
    pub tei: bool,
    /// Explicitly allow namespace-free TEI when `tei` is selected.
    pub allow_no_namespace: bool,
}

impl Default for StructuralOptions {
    fn default() -> Self {
        Self {
            max_bytes: 64 * 1024 * 1024,
            max_nodes: 1_000_000,
            tei: false,
            allow_no_namespace: false,
        }
    }
}

/// Check XML using default limits. A malformed document produces a blocking report.
///
/// The strict parser reports its first failure. Fixing and rechecking can reveal more.
/// DTDs and external entities are never loaded. Input must already be decoded to UTF-8.
pub fn check_xml(source_id: &str, text: &str) -> Result<DiagnosticReport> {
    check_xml_with_options(source_id, text, StructuralOptions::default())
}

/// Check XML and optional TEI boundaries with explicit resource limits.
pub fn check_xml_with_options(
    source_id: &str,
    text: &str,
    options: StructuralOptions,
) -> Result<DiagnosticReport> {
    if text.len() > options.max_bytes {
        return Ok(DiagnosticReport::new(
            source_id,
            text,
            vec![finding(
                "xml_size_limit",
                "Input exceeds the configured XML byte budget",
                vec![],
                "Raise the explicit input budget or split the source before checking",
            )],
        ));
    }
    let parser_options = roxmltree::ParsingOptions {
        allow_dtd: false,
        nodes_limit: options.max_nodes,
        ..Default::default()
    };
    let diagnostics = match roxmltree::Document::parse_with_options(text, parser_options) {
        Ok(document) if options.tei => tei_findings(&document, text, options)?,
        Ok(_) => vec![],
        Err(error) => vec![parse_finding(text, &error)?],
    };
    Ok(DiagnosticReport::new(source_id, text, diagnostics))
}

fn finding(
    code: &str,
    message: impl Into<String>,
    locations: Vec<SourceRange>,
    guidance: &str,
) -> Diagnostic {
    Diagnostic {
        code: code.into(),
        category: DiagnosticCategory::Structural,
        severity: Severity::Error,
        blocking: true,
        score: None,
        certainty: Certainty::Certain,
        message: message.into(),
        locations,
        suggestions: vec![Suggestion {
            message: guidance.into(),
            applicability: Applicability::Review,
            edits: vec![],
        }],
    }
}

fn byte_at(text: &str, pos: roxmltree::TextPos) -> Option<usize> {
    let mut row = 1;
    let mut col = 1;
    for (byte, ch) in text.char_indices() {
        if row == pos.row && col == pos.col {
            return Some(byte);
        }
        if ch == '\n' {
            row += 1;
            col = 1;
        } else {
            col += 1;
        }
    }
    (row == pos.row && col == pos.col).then_some(text.len())
}

fn parse_finding(text: &str, error: &roxmltree::Error) -> Result<Diagnostic> {
    use roxmltree::Error as XmlError;
    // These variants expose only a synthetic 1:1 position, not an exact source location.
    let unlocated = matches!(
        error,
        XmlError::NoRootNode
            | XmlError::UnclosedRootNode
            | XmlError::DtdDetected
            | XmlError::NodesLimitReached
            | XmlError::AttributesLimitReached
            | XmlError::NamespacesLimitReached
            | XmlError::UnexpectedEndOfStream
    );
    let byte = if unlocated {
        None
    } else {
        byte_at(text, error.pos())
    };
    let locations = byte
        .map(|b| SourceRange::from_bytes(text, b..b))
        .transpose()?
        .into_iter()
        .collect();
    let mut issue = finding(
        "xml_parse_error",
        error.to_string(),
        locations,
        "Resolve the parser failure in context, then recheck the complete document",
    );
    match error {
        XmlError::DtdDetected => {
            issue.code = "xml_dtd_unsupported".into();
            issue.suggestions[0].message =
                "Supply self-contained XML without a DTD; do not discard unresolved entities"
                    .into();
        }
        XmlError::NodesLimitReached => {
            issue.code = "xml_node_limit".into();
        }
        XmlError::UnknownEntityReference(_, _) => {
            issue.code = "xml_unknown_entity".into();
        }
        XmlError::UnexpectedCloseTag(expected, actual, _) => {
            issue.code = "xml_tag_mismatch".into();
            if let Some(start) = byte {
                let before = format!("</{actual}>");
                if text[start..].starts_with(&before) {
                    let range = SourceRange::from_bytes(text, start..start + before.len())?;
                    issue.locations = vec![range.clone()];
                    if expected.eq_ignore_ascii_case(actual) {
                        issue.code = "xml_tag_case".into();
                        issue.suggestions = vec![Suggestion {
                            message:
                                "Match the closing tag's case to the opening tag, then revalidate"
                                    .into(),
                            applicability: Applicability::Automatic,
                            edits: vec![TextEdit {
                                range,
                                before,
                                after: format!("</{expected}>"),
                            }],
                        }];
                    }
                }
            }
        }
        XmlError::MalformedEntityReference(_) => {
            if let Some(start) = byte.filter(|b| text[*b..].starts_with('&')) {
                let range = SourceRange::from_bytes(text, start..start + 1)?;
                issue.code = "xml_bare_ampersand".into();
                issue.locations = vec![range.clone()];
                issue.suggestions = vec![Suggestion {
                    message:
                        "Escape the literal ampersand if it was not intended as an entity reference"
                            .into(),
                    applicability: Applicability::Review,
                    edits: vec![TextEdit {
                        range,
                        before: "&".into(),
                        after: "&amp;".into(),
                    }],
                }];
            }
        }
        _ => {}
    }
    Ok(issue)
}

fn tei_findings(
    document: &roxmltree::Document<'_>,
    text: &str,
    options: StructuralOptions,
) -> Result<Vec<Diagnostic>> {
    let root = document.root_element();
    let namespace = root.tag_name().namespace();
    if !matches!(root.tag_name().name(), "TEI" | "teiCorpus")
        || !(namespace == Some(TEI) || namespace.is_none() && options.allow_no_namespace)
    {
        return Ok(vec![finding(
            "tei_root",
            "Expected a TEI or teiCorpus root in the TEI namespace",
            vec![SourceRange::from_bytes(text, root.range())?],
            "Supply TEI namespace http://www.tei-c.org/ns/1.0 or explicitly opt into namespace-free TEI",
        )]);
    }
    let mut issues = vec![];
    let mut ids = HashMap::new();
    let positions = SourceMap::new(text);
    for node in document.descendants().filter(roxmltree::Node::is_element) {
        if let Some(attribute) = node.attribute_node((XML, "id")) {
            let range = attribute.range();
            if let Some(previous) = ids.insert(attribute.value(), range.clone()) {
                issues.push(finding(
                    "tei_duplicate_id",
                    format!("Duplicate xml:id: {}", attribute.value()),
                    vec![positions.range(range)?, positions.range(previous)?],
                    "Assign a unique identity and update references deliberately",
                ));
            }
        }
        let local = node.tag_name().name();
        let unsupported = node.tag_name().namespace() == Some("http://www.w3.org/2001/XInclude")
            || node.attribute("copyOf").is_some()
            || node.attribute("spanTo").is_some()
            || node.tag_name().namespace() == namespace
                && (matches!(
                    local,
                    "sourceDoc"
                        | "subst"
                        | "add"
                        | "del"
                        | "restore"
                        | "transpose"
                        | "listTranspose"
                        | "join"
                        | "alt"
                        | "rdgGrp"
                ) || local == "standOff" && node.children().any(|n| n.is_element()));
        if unsupported {
            issues.push(finding("tei_adapter_required", format!("{local} requires explicit resolution or a dedicated adapter"),
                vec![positions.range(node.range())?],
                "Resolve this construct with an explicit reading policy or adapter; preserve the original source"));
        }
    }
    issues.sort_by_key(|d| d.locations.first().map(|r| r.start.byte));
    Ok(issues)
}
