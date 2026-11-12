//! Bounded, purpose-aware TEI metadata validation. No text is rewritten.

use crate::{
    Error, Result,
    diagnostic::{
        Applicability, Certainty, Diagnostic, DiagnosticCategory, DiagnosticReport, Severity,
        SourceMap, SourceRange, Suggestion,
    },
    structural::{StructuralOptions, check_xml},
};

const TEI: &str = "http://www.tei-c.org/ns/1.0";

/// Structured metadata purposes supported without language guessing.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Serialize, serde::Deserialize),
    serde(rename_all = "snake_case")
)]
pub enum FieldPurpose {
    /// Numeric year, year range, month or Gregorian calendar date.
    Date,
    /// Caller-expected primary document identifier.
    Identifier,
}

/// Whether the bounded purpose policy accepted this field.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[cfg_attr(
    feature = "serde",
    derive(serde::Serialize, serde::Deserialize),
    serde(rename_all = "snake_case")
)]
pub enum FieldStatus {
    /// The selected purpose checks passed; not a full TEI schema acceptance claim.
    Validated,
    /// Unsupported, invalid, or inconsistent; the diagnostic remains blocking.
    Blocked,
}

/// A structured field bound to the exact report source and an XML element locator.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct PurposeField {
    /// Zero-based element-child indices from the document root; root is an empty vector.
    pub element_path: Vec<usize>,
    /// Element namespace URI, or empty for explicitly permitted namespace-free TEI.
    pub namespace: String,
    /// Element local name.
    pub name: String,
    /// Purpose whose policy was evaluated.
    pub purpose: FieldPurpose,
    /// Complete decoded text, before trimming for lexical validation.
    pub value: String,
    /// Exact original XML element range, including its markup.
    pub range: SourceRange,
    /// Original XML ranges for decoded text nodes; entities/CDATA retain lexical ranges.
    pub value_ranges: Vec<SourceRange>,
    /// Validation outcome.
    pub status: FieldStatus,
    /// Associated index in the shared diagnostic array when blocked.
    pub diagnostic_index: Option<usize>,
}

/// Shared diagnostics plus successful/blocked structured-field receipts.
#[derive(Debug, Clone, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct PurposeReport {
    /// The versioned, source-hashed shared report.
    #[cfg_attr(feature = "serde", serde(flatten))]
    pub report: DiagnosticReport,
    /// Fields checked under the bounded purpose policy.
    pub fields: Vec<PurposeField>,
    /// Bounded purpose policy version, currently 1.
    pub policy_version: u16,
    /// Exact identifier expectation supplied by the caller, distinct from source identity.
    pub expected_document_id: Option<String>,
    /// Whether this request explicitly permitted namespace-free TEI.
    pub allow_no_namespace: bool,
}

fn purpose_report(
    source_id: &str,
    text: &str,
    expected_document_id: Option<&str>,
    allow_no_namespace: bool,
) -> Result<PurposeReport> {
    Ok(PurposeReport {
        report: check_xml(source_id, text)?,
        fields: vec![],
        policy_version: 1,
        expected_document_id: expected_document_id.map(str::to_owned),
        allow_no_namespace,
    })
}

type Point = (u16, u8, u8);
type Bounds = (Point, Point);

fn year(value: &str) -> Option<u16> {
    (value.len() == 4 && value.bytes().all(|b| b.is_ascii_digit()))
        .then(|| value.parse::<u16>().ok())
        .flatten()
        .filter(|y| *y > 0)
}

const fn month_days(year: u16, month: u8) -> u8 {
    match month {
        4 | 6 | 9 | 11 => 30,
        2 if year.is_multiple_of(400) || year.is_multiple_of(4) && !year.is_multiple_of(100) => 29,
        2 => 28,
        _ => 31,
    }
}

fn atom(value: &str) -> Option<Bounds> {
    let parts: Vec<_> = value.split('-').collect();
    let y = year(parts[0])?;
    if parts.len() == 1 {
        return Some(((y, 1, 1), (y, 12, 31)));
    }
    if parts.len() > 3 || parts[1].len() != 2 || !parts[1].bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let m = parts[1]
        .parse::<u8>()
        .ok()
        .filter(|m| (1..=12).contains(m))?;
    let last = month_days(y, m);
    if parts.len() == 2 {
        return Some(((y, m, 1), (y, m, last)));
    }
    if parts[2].len() != 2 || !parts[2].bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let d = parts[2]
        .parse::<u8>()
        .ok()
        .filter(|d| (1..=last).contains(d))?;
    Some(((y, m, d), (y, m, d)))
}

fn date_value(value: &str) -> Option<Bounds> {
    if let Some((a, b)) = value
        .split_once('–')
        .or_else(|| (value.len() == 9).then(|| value.split_once('-')).flatten())
    {
        let first = year(a)?;
        let last = year(b)?;
        return (first <= last).then_some(((first, 1, 1), (last, 12, 31)));
    }
    atom(value)
}

fn date_problem(
    node: roxmltree::Node<'_, '_>,
) -> Option<(&'static str, &'static str, Option<std::ops::Range<usize>>)> {
    if let Some(a) = node.attributes().find(|a| {
        a.namespace().is_none()
            && (matches!(a.name(), "calendar" | "datingMethod" | "datingPoint")
                || a.name().ends_with("-iso")
                || a.name().ends_with("-custom"))
    }) {
        return Some((
            "tei_date_unsupported",
            "Calendar/dating-system attributes require a dedicated date policy",
            Some(a.range()),
        ));
    }
    let label: String = node
        .children()
        .filter(roxmltree::Node::is_text)
        .filter_map(|n| n.text())
        .collect();
    let mut bounds = ((1, 1, 1), (9999, 12, 31));
    let mut has_value = if label.trim().is_empty() {
        false
    } else {
        let Some(parsed) = date_value(label.trim()) else {
            return Some((
                "tei_date_invalid",
                "Expected a numeric year, ordered year range, month or valid calendar date",
                None,
            ));
        };
        bounds = parsed;
        true
    };
    for name in ["when", "from", "to", "notBefore", "notAfter"] {
        if let Some(a) = node.attribute_node(name) {
            let Some((low, high)) = atom(a.value().trim()) else {
                return Some((
                    "tei_date_attribute_invalid",
                    "Date attribute is outside the supported calendar forms",
                    Some(a.range()),
                ));
            };
            has_value = true;
            if matches!(name, "when" | "from" | "notBefore") {
                bounds.0 = bounds.0.max(low);
            }
            if matches!(name, "when" | "to" | "notAfter") {
                bounds.1 = bounds.1.min(high);
            }
            if bounds.0 > bounds.1 {
                return Some((
                    "tei_date_inconsistent",
                    "Date text and temporal attributes have no consistent interval",
                    Some(a.range()),
                ));
            }
        }
    }
    (!has_value).then_some((
        "tei_date_missing",
        "Date has neither a supported text value nor temporal attributes",
        None,
    ))
}

fn primary_identifier(node: roxmltree::Node<'_, '_>, root: roxmltree::Node<'_, '_>) -> bool {
    let mut current = node.parent_element();
    for name in ["publicationStmt", "fileDesc", "teiHeader"] {
        let Some(parent) = current else {
            return false;
        };
        if parent.tag_name().namespace() != node.tag_name().namespace()
            || parent.tag_name().name() != name
        {
            return false;
        }
        current = parent.parent_element();
    }
    root.tag_name().name() == "TEI"
        && root.tag_name().namespace() == node.tag_name().namespace()
        && current == Some(root)
}

type Problem = (&'static str, String, Option<std::ops::Range<usize>>);

fn field_problem(
    node: roxmltree::Node<'_, '_>,
    root: roxmltree::Node<'_, '_>,
    purpose: FieldPurpose,
    value: &str,
    expected_document_id: Option<&str>,
) -> Option<Problem> {
    if node.children().any(|n| n.is_element()) {
        Some((
            "tei_field_markup",
            "Structured date/identifier contains child markup; explicit resolution is required"
                .to_owned(),
            Some(node.range()),
        ))
    } else if purpose == FieldPurpose::Date {
        date_problem(node).map(|(code, message, location)| (code, message.to_owned(), location))
    } else if node.attribute("type").is_some()
        || node.attribute("subtype").is_some()
        || !primary_identifier(node, root)
        || expected_document_id.is_none()
    {
        Some((
            "tei_identifier_policy_required",
            "Identifier needs a type/scope-specific identity policy".to_owned(),
            None,
        ))
    } else if value.trim().is_empty() || value.trim().chars().any(char::is_whitespace) {
        Some((
            "tei_identifier_invalid",
            "Primary document identifier must be nonempty and contain no whitespace".to_owned(),
            None,
        ))
    } else if Some(value.trim()) != expected_document_id {
        Some((
            "tei_identifier_mismatch",
            format!(
                "Encoded identifier {:?} differs from caller expectation {:?}",
                value.trim(),
                expected_document_id
            ),
            None,
        ))
    } else {
        None
    }
}

/// Validate structured TEI metadata while retaining exact raw XML locations.
///
/// `expected_document_id` is an explicit caller policy, not a filename convention in core.
/// It applies only to an untyped primary publication identifier of a single root TEI.
/// Typed IDs and collection-member IDs remain blocked pending a suitable identity policy.
/// DTDs, oversized XML and parser failures use the shared structural diagnostics.
/// Gregorian numeric forms are bounded checks, not full TEI P5 schema validation.
pub fn validate_tei_metadata(
    source_id: &str,
    text: &str,
    expected_document_id: Option<&str>,
    allow_no_namespace: bool,
) -> Result<PurposeReport> {
    let mut output = purpose_report(source_id, text, expected_document_id, allow_no_namespace)?;
    if !output.report.passed() {
        return Ok(output);
    }
    let report = &mut output.report;
    let fields = &mut output.fields;
    let options = StructuralOptions::default();
    let doc = roxmltree::Document::parse_with_options(
        text,
        roxmltree::ParsingOptions {
            allow_dtd: false,
            nodes_limit: options.max_nodes,
            ..Default::default()
        },
    )
    .map_err(|e| Error::conversion(e.to_string()))?;
    let root = doc.root_element();
    let positions = SourceMap::new(text);
    let mut stack = vec![(root, Vec::new(), false, false)];
    while let Some((node, path, in_metadata, inside_field)) = stack.pop() {
        let ns = node.tag_name().namespace();
        let tei = ns == Some(TEI) || ns.is_none() && allow_no_namespace;
        let local = node.tag_name().name();
        let metadata = in_metadata
            || tei
                && matches!(
                    local,
                    "teiHeader" | "titlePage" | "docTitle" | "docAuthor" | "docImprint"
                );
        let purpose = match (tei && metadata && !inside_field, local) {
            (true, "date") => Some(FieldPurpose::Date),
            (true, "idno") => Some(FieldPurpose::Identifier),
            _ => None,
        };
        if let Some(purpose) = purpose {
            let value: String = node
                .descendants()
                .filter(roxmltree::Node::is_text)
                .filter_map(|n| n.text())
                .collect();
            let value_ranges = node
                .descendants()
                .filter(roxmltree::Node::is_text)
                .map(|n| positions.range(n.range()))
                .collect::<Result<Vec<_>>>()?;
            let range = positions.range(node.range())?;
            let problem = field_problem(node, root, purpose, &value, expected_document_id);
            let diagnostic_index = if let Some((code, message, attribute_range)) = problem {
                let index = report.diagnostics.len();
                let mut locations = attribute_range
                    .map(|r| positions.range(r))
                    .transpose()?
                    .into_iter()
                    .collect::<Vec<_>>();
                locations.extend(value_ranges.iter().cloned());
                if locations.is_empty() {
                    locations.push(range.clone());
                }
                report.diagnostics.push(Diagnostic { code: code.into(), category: DiagnosticCategory::Structural,
                    severity: Severity::Error, blocking: true, score: None, certainty: Certainty::Certain,
                    message, locations, suggestions: vec![Suggestion { applicability: Applicability::Review,
                        message: if purpose == FieldPurpose::Identifier {
                            "Review the identity expectation and references; preserve the encoded identifier until deliberately resolved"
                        } else { "Review the date expression and attributes under the intended dating policy" }.into(), edits: vec![] }] });
                Some(index)
            } else {
                None
            };
            fields.push(PurposeField {
                element_path: path.clone(),
                namespace: ns.unwrap_or("").into(),
                name: local.into(),
                purpose,
                value,
                range,
                value_ranges,
                status: if diagnostic_index.is_some() {
                    FieldStatus::Blocked
                } else {
                    FieldStatus::Validated
                },
                diagnostic_index,
            });
        }
        let mut index = node.children().filter(roxmltree::Node::is_element).count();
        for child in node.children().rev().filter(roxmltree::Node::is_element) {
            index -= 1;
            let mut child_path = path.clone();
            child_path.push(index);
            stack.push((
                child,
                child_path,
                metadata,
                inside_field || purpose.is_some(),
            ));
        }
    }
    Ok(output)
}
