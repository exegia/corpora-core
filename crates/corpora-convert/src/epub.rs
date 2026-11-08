//! Bounded EPUB reading projection. Validation never changes source bytes.

use corpora_core::diagnostic::{
    Applicability, Certainty, Diagnostic, DiagnosticCategory, DiagnosticReport, Severity,
    SourceRange, Suggestion,
};
use roxmltree::{Document, Node};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{Cursor, Read};
use zip::ZipArchive;

const MAX_MEMBERS: usize = 1024;
const MAX_ARCHIVE_BYTES: usize = 80 * 1024 * 1024;
const MAX_MEMBER_BYTES: u64 = 16 * 1024 * 1024;
const MAX_EXPANDED_BYTES: u64 = 64 * 1024 * 1024;
const MAX_SLOTS: usize = 1_000_000;

/// One archive member and the hash of its exact expanded bytes.
#[derive(Debug, Serialize)]
pub struct Member {
    /// Archive-relative name, never a filesystem extraction path.
    pub name: String,
    /// SHA-256 of expanded member bytes.
    pub sha256: String,
    /// Expanded byte count.
    pub bytes: usize,
}

/// An XHTML element over Unicode scalar positions in the projected text.
#[derive(Debug, Serialize)]
pub struct Element {
    /// Preorder key, stable within this source member.
    pub key: String,
    /// Parent preorder key.
    pub parent: Option<String>,
    /// Local XHTML tag name.
    pub tag: String,
    /// Exact attributes in source order-independent form.
    pub attributes: BTreeMap<String, String>,
    /// Inclusive scalar start in this document's reading string.
    pub start: usize,
    /// Exclusive scalar end.
    pub end: usize,
}

/// Reading content from one linear spine item.
#[derive(Debug, Serialize)]
pub struct ReadingDocument {
    /// Manifest ID for this spine item.
    pub id: String,
    /// Archive member name.
    pub member: String,
    /// XHTML text in DOM order, without inserted whitespace.
    pub text: String,
    /// Complete non-empty XHTML hierarchy.
    pub elements: Vec<Element>,
}

/// Member-scoped diagnostics use offsets in expanded UTF-8 member bytes.
#[derive(Debug, Serialize)]
pub struct MemberReport {
    /// Member name, or archive-level marker when no member can be identified.
    pub member: String,
    /// Shared diagnostic contract bound to the expanded source string.
    pub report: DiagnosticReport,
}

/// Reusable EPUB validation result. A blocking finding forbids export.
#[derive(Debug, Serialize)]
pub struct EpubReport {
    /// Original archive SHA-256.
    pub archive_sha256: String,
    /// Expanded member inventory.
    pub members: Vec<Member>,
    /// OPF unique identifier value.
    pub identifier: Option<String>,
    /// Publication metadata, separate from reading text.
    pub metadata: BTreeMap<String, Vec<String>>,
    /// Navigation resources excluded from reading text.
    pub navigation: Vec<String>,
    /// Linear spine content only, in spine order.
    pub documents: Vec<ReadingDocument>,
    /// Actionable findings, with member-local source coordinates where possible.
    pub findings: Vec<MemberReport>,
}

impl EpubReport {
    /// Whether every checked boundary is safe for this conversion policy.
    pub fn passed(&self) -> bool {
        self.findings.iter().all(|finding| finding.report.passed()) && !self.documents.is_empty()
    }

    fn finding(
        &mut self,
        member: &str,
        source: &str,
        code: &str,
        message: &str,
        offset: Option<usize>,
        blocking: bool,
    ) {
        let locations = offset
            .and_then(|byte| SourceRange::from_bytes(source, byte..byte).ok())
            .into_iter()
            .collect();
        let diagnostic = Diagnostic {
            code: code.into(),
            category: DiagnosticCategory::Structural,
            severity: if blocking {
                Severity::Error
            } else {
                Severity::Warning
            },
            blocking,
            score: None,
            certainty: Certainty::Certain,
            message: message.into(),
            locations,
            suggestions: vec![Suggestion {
                message: format!("Correct {member} in the source EPUB and revalidate"),
                applicability: Applicability::Review,
                edits: vec![],
            }],
        };
        self.findings.push(MemberReport {
            member: member.into(),
            report: DiagnosticReport::new(member, source, vec![diagnostic]),
        });
    }
}

fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn safe_path(path: &str) -> bool {
    !path.is_empty()
        && !path.starts_with('/')
        && !path.contains('\\')
        && !path
            .split('/')
            .any(|part| part.is_empty() || part == "." || part == "..")
        && !path.contains(':')
}

fn relative_path(base: &str, href: &str) -> Option<String> {
    if href.contains('?') {
        return None;
    }
    let resource = href.split(['#', '?']).next()?;
    if resource.starts_with('/') || resource.contains('\\') || resource.contains(':') {
        return None;
    }
    let mut parts: Vec<&str> = base.split('/').collect();
    parts.pop();
    for part in resource.split('/') {
        match part {
            "" | "." => return None,
            ".." => {
                parts.pop()?;
            }
            _ => parts.push(part),
        }
    }
    let path = parts.join("/");
    safe_path(&path).then_some(path)
}

fn xml<'a>(report: &mut EpubReport, member: &str, source: &'a str) -> Option<Document<'a>> {
    if let Some(offset) = source.find("<!DOCTYPE") {
        report.finding(
            member,
            source,
            "EPUB_XML_DTD",
            "DOCTYPE is unsupported; external entities are never loaded",
            Some(offset),
            true,
        );
        return None;
    }
    match Document::parse(source) {
        Ok(tree) => Some(tree),
        Err(error) => {
            let line = error.pos().row as usize;
            let column = error.pos().col as usize;
            let offset = source
                .split_inclusive('\n')
                .take(line.saturating_sub(1))
                .map(str::len)
                .sum::<usize>()
                + column.saturating_sub(1);
            report.finding(
                member,
                source,
                "EPUB_XML",
                &format!("Malformed XML: {error}"),
                Some(offset.min(source.len())),
                true,
            );
            None
        }
    }
}

fn child<'a, 'i>(node: Node<'a, 'i>, name: &str) -> Option<Node<'a, 'i>> {
    node.children()
        .find(|n| n.is_element() && n.tag_name().name() == name)
}

fn append_text(
    node: Node<'_, '_>,
    parent: Option<&str>,
    text: &mut String,
    elements: &mut Vec<Element>,
    counter: &mut usize,
) {
    if node.is_text() {
        text.push_str(node.text().unwrap_or(""));
        return;
    }
    if !node.is_element() {
        return;
    }
    *counter += 1;
    let key = counter.to_string();
    let start = text.chars().count();
    let index = elements.len();
    elements.push(Element {
        key: key.clone(),
        parent: parent.map(str::to_owned),
        tag: node.tag_name().name().into(),
        attributes: node
            .attributes()
            .map(|attr| (attr.name().into(), attr.value().into()))
            .collect(),
        start,
        end: start,
    });
    for nested in node.children() {
        append_text(nested, Some(&key), text, elements, counter);
    }
    elements[index].end = text.chars().count();
}

/// Validate a local EPUB byte snapshot and project its linear XHTML content.
///
/// No archive member is extracted to disk. Limits are checked before expansion.
/// Only UTF-8 XML, unencrypted reflowable XHTML and linear spine content are supported.
/// Notes and non-linear spine items block export; navigation and metadata are excluded.
#[expect(
    clippy::too_many_lines,
    reason = "single pass keeps archive and XML lifetime-bound sources together"
)]
pub fn validate_epub(bytes: &[u8]) -> EpubReport {
    let mut result = EpubReport {
        archive_sha256: hash(bytes),
        members: vec![],
        identifier: None,
        metadata: BTreeMap::new(),
        navigation: vec![],
        documents: vec![],
        findings: vec![],
    };
    if bytes.len() > MAX_ARCHIVE_BYTES {
        result.finding(
            "<archive>",
            "",
            "EPUB_LIMIT",
            "Original archive exceeds 80 MiB",
            None,
            true,
        );
        return result;
    }
    let Ok(mut archive) = ZipArchive::new(Cursor::new(bytes)) else {
        result.finding(
            "<archive>",
            "",
            "EPUB_ZIP",
            "Input is not a readable ZIP archive",
            None,
            true,
        );
        return result;
    };
    if archive.len() > MAX_MEMBERS {
        result.finding(
            "<archive>",
            "",
            "EPUB_LIMIT",
            "Archive exceeds 1024 members",
            None,
            true,
        );
        return result;
    }
    let mut expanded = 0_u64;
    let mut sources = BTreeMap::<String, Vec<u8>>::new();
    for index in 0..archive.len() {
        let Ok(file) = archive.by_index(index) else {
            continue;
        };
        let name = file.name().to_owned();
        if file.is_dir() {
            if !safe_path(name.trim_end_matches('/')) {
                result.finding(
                    &name,
                    "",
                    "EPUB_PATH",
                    "Unsafe directory member",
                    None,
                    true,
                );
            }
            continue;
        }
        if !safe_path(&name) || sources.contains_key(&name) {
            result.finding(
                &name,
                "",
                "EPUB_PATH",
                "Unsafe, directory or duplicate archive member",
                None,
                true,
            );
            continue;
        }
        expanded = expanded.saturating_add(file.size());
        if file.size() > MAX_MEMBER_BYTES || expanded > MAX_EXPANDED_BYTES {
            result.finding(
                &name,
                "",
                "EPUB_LIMIT",
                "Expanded member exceeds 16 MiB or archive exceeds 64 MiB",
                None,
                true,
            );
            return result;
        }
        let mut data = Vec::new();
        if file
            .take(MAX_MEMBER_BYTES + 1)
            .read_to_end(&mut data)
            .is_err()
            || data.len() as u64 > MAX_MEMBER_BYTES
        {
            result.finding(
                &name,
                "",
                "EPUB_ZIP",
                "Member cannot be expanded within limit",
                None,
                true,
            );
            return result;
        }
        result.members.push(Member {
            name: name.clone(),
            sha256: hash(&data),
            bytes: data.len(),
        });
        sources.insert(name, data);
    }
    if sources.contains_key("META-INF/encryption.xml") {
        result.finding(
            "META-INF/encryption.xml",
            "",
            "EPUB_ENCRYPTED",
            "Encrypted EPUB resources are unsupported",
            None,
            true,
        );
    }
    let Some(container) = sources.get("META-INF/container.xml") else {
        result.finding(
            "META-INF/container.xml",
            "",
            "EPUB_CONTAINER",
            "Missing container.xml",
            None,
            true,
        );
        return result;
    };
    let Ok(container) = std::str::from_utf8(container) else {
        result.finding(
            "META-INF/container.xml",
            "",
            "EPUB_ENCODING",
            "Container must be UTF-8",
            None,
            true,
        );
        return result;
    };
    let Some(tree) = xml(&mut result, "META-INF/container.xml", container) else {
        return result;
    };
    let rootfiles: Vec<_> = tree
        .descendants()
        .filter(|n| n.has_tag_name("rootfile"))
        .collect();
    if rootfiles.len() != 1 {
        result.finding(
            "META-INF/container.xml",
            container,
            "EPUB_CONTAINER",
            "Exactly one rootfile is required",
            None,
            true,
        );
        return result;
    }
    let Some(opf_path) = rootfiles[0].attribute("full-path").filter(|p| safe_path(p)) else {
        result.finding(
            "META-INF/container.xml",
            container,
            "EPUB_PATH",
            "Rootfile path is missing or unsafe",
            Some(rootfiles[0].range().start),
            true,
        );
        return result;
    };
    let Some(opf) = sources.get(opf_path) else {
        result.finding(
            "META-INF/container.xml",
            container,
            "EPUB_OPF",
            "Rootfile target is absent",
            Some(rootfiles[0].range().start),
            true,
        );
        return result;
    };
    let Ok(opf) = std::str::from_utf8(opf) else {
        result.finding(
            opf_path,
            "",
            "EPUB_ENCODING",
            "OPF must be UTF-8",
            None,
            true,
        );
        return result;
    };
    let Some(tree) = xml(&mut result, opf_path, opf) else {
        return result;
    };
    let root = tree.root_element();
    if root.tag_name().name() != "package"
        || root.tag_name().namespace() != Some("http://www.idpf.org/2007/opf")
    {
        result.finding(
            opf_path,
            opf,
            "EPUB_OPF",
            "Root must be package",
            Some(root.range().start),
            true,
        );
        return result;
    }
    if root
        .attribute("version")
        .is_none_or(|v| !v.starts_with('2') && !v.starts_with('3'))
    {
        result.finding(
            opf_path,
            opf,
            "EPUB_VERSION",
            "Only EPUB 2 and 3 package versions are supported",
            Some(root.range().start),
            true,
        );
    }
    let Some(metadata) = child(root, "metadata") else {
        result.finding(
            opf_path,
            opf,
            "EPUB_METADATA",
            "Missing metadata",
            None,
            true,
        );
        return result;
    };
    let ids: Vec<_> = metadata
        .children()
        .filter(|n| n.is_element() && n.tag_name().name() == "identifier")
        .collect();
    let unique = root.attribute("unique-identifier").unwrap_or("");
    let matched: Vec<_> = ids
        .iter()
        .filter(|n| n.attribute("id") == Some(unique))
        .collect();
    if unique.is_empty()
        || matched.len() != 1
        || matched[0].text().is_none_or(|s| s.trim().is_empty())
    {
        result.finding(
            opf_path,
            opf,
            "EPUB_IDENTIFIER",
            "OPF unique-identifier must name exactly one nonempty metadata identifier",
            Some(root.range().start),
            true,
        );
    } else {
        result.identifier = matched[0].text().map(str::to_owned);
    }
    for entry in metadata.children().filter(Node::is_element) {
        if entry.children().any(|node| node.is_element()) {
            result.finding(
                opf_path,
                opf,
                "EPUB_METADATA",
                "Nested metadata markup is unsupported",
                Some(entry.range().start),
                true,
            );
        }
        result
            .metadata
            .entry(entry.tag_name().name().into())
            .or_default()
            .push(entry.text().unwrap_or("").into());
    }
    if result
        .metadata
        .get("meta")
        .is_some_and(|values| values.iter().any(|v| v.contains("fixed-layout")))
        || metadata.descendants().any(|n| {
            n.is_element()
                && n.attribute("property") == Some("rendition:layout")
                && n.text() == Some("pre-paginated")
        })
    {
        result.finding(
            opf_path,
            opf,
            "EPUB_LAYOUT",
            "Fixed layout is unsupported",
            Some(metadata.range().start),
            true,
        );
    }
    let Some(manifest) = child(root, "manifest") else {
        result.finding(
            opf_path,
            opf,
            "EPUB_MANIFEST",
            "Missing manifest",
            None,
            true,
        );
        return result;
    };
    let mut items = BTreeMap::new();
    for item in manifest.children().filter(|n| n.has_tag_name("item")) {
        let id = item.attribute("id").unwrap_or("");
        let href = item.attribute("href").unwrap_or("");
        let Some(path) = relative_path(opf_path, href) else {
            result.finding(
                opf_path,
                opf,
                "EPUB_PATH",
                "Unsafe manifest href",
                Some(item.range().start),
                true,
            );
            continue;
        };
        if id.is_empty()
            || items
                .insert(
                    id.to_owned(),
                    (
                        path.clone(),
                        item.attribute("media-type").unwrap_or("").to_owned(),
                        item.attribute("properties").unwrap_or("").to_owned(),
                    ),
                )
                .is_some()
        {
            result.finding(
                opf_path,
                opf,
                "EPUB_MANIFEST",
                "Missing or duplicate manifest ID",
                Some(item.range().start),
                true,
            );
        }
        if !sources.contains_key(&path) {
            result.finding(
                opf_path,
                opf,
                "EPUB_MANIFEST",
                &format!("Missing manifest target: {path}"),
                Some(item.range().start),
                true,
            );
        }
    }
    let Some(spine) = child(root, "spine") else {
        result.finding(opf_path, opf, "EPUB_SPINE", "Missing spine", None, true);
        return result;
    };
    let nav_paths: BTreeSet<_> = items
        .values()
        .filter(|(_, _, properties)| properties.split_whitespace().any(|p| p == "nav"))
        .map(|(path, _, _)| path.as_str())
        .collect();
    result.navigation = nav_paths.iter().map(|p| (*p).to_owned()).collect();
    if let Some(toc) = spine.attribute("toc") {
        if let Some((path, _, _)) = items.get(toc) {
            result.navigation.push(path.clone());
            result.navigation.sort();
            result.navigation.dedup();
        } else {
            result.finding(
                opf_path,
                opf,
                "EPUB_NAV",
                "Spine toc references a missing NCX manifest ID",
                Some(spine.range().start),
                true,
            );
        }
    }
    let mut seen_spine = BTreeSet::new();
    for itemref in spine.children().filter(|n| n.has_tag_name("itemref")) {
        let idref = itemref.attribute("idref").unwrap_or("");
        if !seen_spine.insert(idref) {
            result.finding(
                opf_path,
                opf,
                "EPUB_SPINE",
                "Duplicate spine reference is unsupported",
                Some(itemref.range().start),
                true,
            );
        }
        if itemref.attribute("linear") == Some("no") {
            result.finding(
                opf_path,
                opf,
                "EPUB_NONLINEAR",
                "Non-linear spine items require an explicit reading policy",
                Some(itemref.range().start),
                true,
            );
            continue;
        }
        let Some((path, media, _)) = items.get(idref) else {
            result.finding(
                opf_path,
                opf,
                "EPUB_SPINE",
                &format!("Missing manifest ID for spine reference: {idref}"),
                Some(itemref.range().start),
                true,
            );
            continue;
        };
        if nav_paths.contains(path.as_str()) {
            result.finding(
                opf_path,
                opf,
                "EPUB_NAV",
                "Navigation cannot be a reading spine item",
                Some(itemref.range().start),
                true,
            );
            continue;
        }
        if media != "application/xhtml+xml" {
            result.finding(
                opf_path,
                opf,
                "EPUB_MEDIA",
                "Linear spine content must be XHTML",
                Some(itemref.range().start),
                true,
            );
            continue;
        }
        let Some(data) = sources.get(path) else {
            continue;
        };
        let Ok(source) = std::str::from_utf8(data) else {
            result.finding(path, "", "EPUB_ENCODING", "XHTML must be UTF-8", None, true);
            continue;
        };
        let Some(xhtml) = xml(&mut result, path, source) else {
            continue;
        };
        if xhtml.root_element().tag_name().namespace() != Some("http://www.w3.org/1999/xhtml") {
            result.finding(
                path,
                source,
                "EPUB_XHTML",
                "Reading resource must use the XHTML namespace",
                Some(xhtml.root_element().range().start),
                true,
            );
            continue;
        }
        let Some(body) = xhtml.descendants().find(|n| n.has_tag_name("body")) else {
            result.finding(path, source, "EPUB_XHTML", "Missing XHTML body", None, true);
            continue;
        };
        if body.descendants().any(|n| {
            n.is_element()
                && matches!(
                    n.tag_name().name(),
                    "script"
                        | "iframe"
                        | "object"
                        | "embed"
                        | "svg"
                        | "math"
                        | "img"
                        | "audio"
                        | "video"
                )
        }) {
            result.finding(
                path,
                source,
                "EPUB_CONTENT",
                "Embedded, scripted, image or media reading content is unsupported",
                Some(body.range().start),
                true,
            );
        }
        if let Some(note) = body.descendants().find(|n| {
            n.is_element() && n.attribute("epub:type").is_some_and(|v| v.contains("note"))
                || n.attribute(("http://www.idpf.org/2007/ops", "type"))
                    .is_some_and(|v| v.contains("note"))
        }) {
            result.finding(
                path,
                source,
                "EPUB_NOTE",
                "Notes require a separate reading projection policy",
                Some(note.range().start),
                true,
            );
        }
        let mut text = String::new();
        let mut elements = vec![];
        let mut counter = 0;
        append_text(body, None, &mut text, &mut elements, &mut counter);
        if text.chars().count() > MAX_SLOTS
            || result
                .documents
                .iter()
                .map(|d| d.text.chars().count())
                .sum::<usize>()
                + text.chars().count()
                > MAX_SLOTS
        {
            result.finding(
                path,
                source,
                "EPUB_LIMIT",
                "Reading projection exceeds one million character slots",
                Some(body.range().start),
                true,
            );
        }
        result.documents.push(ReadingDocument {
            id: idref.into(),
            member: path.clone(),
            text,
            elements,
        });
    }
    if result.documents.is_empty() {
        result.finding(
            opf_path,
            opf,
            "EPUB_SPINE",
            "No supported linear reading content",
            Some(spine.range().start),
            true,
        );
    }
    result
}
