//! Bounded EPUB reading projection. Validation never changes source bytes.

use corpora_core::diagnostic::{
    Applicability, Certainty, Diagnostic, DiagnosticCategory, DiagnosticReport, Severity,
    SourceRange, Suggestion,
};
use roxmltree::{Document, Node, ParsingOptions};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::{Cursor, Read};
use zip::ZipArchive;

const MAX_MEMBERS: usize = 1024;
const MAX_ARCHIVE_BYTES: usize = 80 * 1024 * 1024;
const MAX_MEMBER_BYTES: u64 = 16 * 1024 * 1024;
const MAX_EXPANDED_BYTES: u64 = 64 * 1024 * 1024;
/// Default character-slot bound for normal EPUB validation.
pub const DEFAULT_MAX_SLOTS: usize = 1_000_000;
/// Hard character-slot ceiling for explicitly requested large conversions.
pub const HARD_MAX_SLOTS: usize = 8_000_000;

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
    /// Projection preorder key, stable within this document or note.
    pub key: String,
    /// Parent preorder key.
    pub parent: Option<String>,
    /// Local XHTML tag name.
    pub tag: String,
    /// Exact attributes in source order-independent form.
    pub attributes: BTreeMap<String, String>,
    /// Expanded UTF-8 source-member byte offset of the opening element.
    pub source_byte: usize,
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
    /// Complete XHTML hierarchy, including empty elements.
    pub elements: Vec<Element>,
}

/// A note body excluded from the main reading stream but retained as text.
#[derive(Debug, Serialize)]
pub struct NoteBody {
    /// Stable EPUB identity: archive member plus XHTML fragment ID.
    pub source_key: String,
    /// Source archive member.
    pub member: String,
    /// XHTML fragment ID.
    pub fragment: String,
    /// Raw byte offset of the note element in its expanded UTF-8 member.
    pub source_byte: usize,
    /// EPUB note kind, `footnote` or `endnote`.
    pub kind: String,
    /// Exact decoded XHTML text of the note body.
    pub text: String,
    /// Source XHTML hierarchy inside this note, including empty elements.
    pub elements: Vec<Element>,
}

/// A note marker retained in main text and linked to a note body.
#[derive(Debug, Serialize)]
pub struct NoteReference {
    /// Manifest ID of the containing linear spine item.
    pub document_id: String,
    /// Source archive member containing the marker.
    pub member: String,
    /// Preorder key of the marker's XHTML element.
    pub anchor_key: String,
    /// Original EPUB link target.
    pub href: String,
    /// Exact marker text (never generated numbering).
    pub label: String,
    /// Resolved stable note identity.
    pub target_key: String,
    /// Raw byte offset in the expanded UTF-8 source member.
    pub source_byte: usize,
}

/// A referenced non-text resource retained outside character slots.
#[derive(Clone, Debug, Serialize)]
pub struct AssetReference {
    /// Manifest ID of the containing spine item.
    pub document_id: String,
    /// `document` or `note`; offsets are relative to this reading scope.
    pub scope: String,
    /// Manifest ID for a document or `member#fragment` for a note.
    pub scope_id: String,
    /// `image`, `audio`, or `video`.
    pub kind: String,
    /// XHTML member containing the image element.
    pub member: String,
    /// Element key in the reading projection.
    pub element_key: String,
    /// Original `src` attribute.
    pub href: String,
    /// Resolved archive member, checked against the OPF manifest.
    pub target_member: String,
    /// Manifest-declared media type.
    pub media_type: String,
    /// Hash of exact expanded image bytes.
    pub sha256: String,
    /// Expanded image byte count.
    pub bytes: usize,
    /// Original alternative text, possibly empty for decorative images.
    pub alt: String,
    /// Zero-width position in the main reading text, in Unicode scalars.
    pub text_offset: usize,
    /// Raw byte offset of the `img` element in the expanded XHTML member.
    pub source_byte: usize,
    /// Exclusive expanded-member byte end for an inline XML asset.
    pub source_end: Option<usize>,
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
    /// Note bodies, outside document text, in deterministic source order.
    pub notes: Vec<NoteBody>,
    /// Validated marker-to-note links.
    pub note_references: Vec<NoteReference>,
    /// Image assets at exact source and reading-text positions.
    pub images: Vec<AssetReference>,
    /// All referenced non-text assets, including images and media.
    pub assets: Vec<AssetReference>,
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

fn passive_svg(bytes: &[u8]) -> bool {
    let Ok(source) = std::str::from_utf8(bytes) else {
        return false;
    };
    let Ok(tree) = Document::parse(source) else {
        return false;
    };
    tree.root_element().tag_name().namespace() == Some("http://www.w3.org/2000/svg")
        && tree.descendants().filter(Node::is_element).all(|element| {
            !matches!(
                element.tag_name().name(),
                "script" | "foreignObject" | "image"
            ) && element.attributes().all(|attribute| {
                !attribute.name().starts_with("on")
                    && !attribute.value().contains("http:")
                    && !attribute.value().contains("https:")
                    && !attribute.value().contains("javascript:")
                    && !attribute.value().contains("data:")
            })
        })
}

fn supported_asset_type(kind: &str, media: &str) -> bool {
    match kind {
        "image" => media.starts_with("image/"),
        "audio" => media.starts_with("audio/"),
        "video" => media.starts_with("video/"),
        "track" => media == "text/vtt" || media == "application/ttml+xml",
        "object" | "embed" => {
            media.starts_with("image/")
                || media.starts_with("audio/")
                || media.starts_with("video/")
                || media == "application/pdf"
        }
        _ => false,
    }
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

fn xml<'a>(
    report: &mut EpubReport,
    member: &str,
    source: &'a str,
    xhtml: bool,
) -> Option<Document<'a>> {
    let allow_dtd = if let Some(offset) = source.find("<!DOCTYPE") {
        let end = source[offset..].find('>').map(|relative| offset + relative);
        let declaration = end.and_then(|last| source.get(offset..=last));
        let normalized =
            declaration.map(|text| text.split_whitespace().collect::<Vec<_>>().join(" "));
        let known = matches!(
            normalized.as_deref(),
            Some(
                "<!DOCTYPE html>"
                    | "<!DOCTYPE html PUBLIC \"-//W3C//DTD XHTML 1.1//EN\" \"http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd\">"
            )
        );
        if !xhtml || !known {
            report.finding(member, source, "EPUB_XML_DTD", "Only the bounded XHTML 1.1 or HTML doctype is supported; external entities are never loaded", Some(offset), true);
            return None;
        }
        true
    } else {
        false
    };
    let options = ParsingOptions {
        allow_dtd,
        nodes_limit: 1_000_000,
        entity_resolver: None,
    };
    match Document::parse_with_options(source, options) {
        Ok(tree) => Some(tree),
        Err(error) => {
            let line = error.pos().row as usize;
            let column = error.pos().col as usize;
            let offset = source
                .split_inclusive('\n')
                .take(line.saturating_sub(1))
                .map(str::len)
                .sum::<usize>();
            let offset = offset
                + source[offset..]
                    .chars()
                    .take(column.saturating_sub(1))
                    .map(char::len_utf8)
                    .sum::<usize>();
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
    owner: &AssetOwner<'_>,
    assets: &mut Vec<AssetReference>,
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
        source_byte: node.range().start,
        start,
        end: start,
    });
    if push_assets(node, &key, start, owner, assets) {
        return;
    }
    for nested in node.children() {
        append_text(nested, Some(&key), text, elements, counter, owner, assets);
    }
    elements[index].end = text.chars().count();
}

fn epub_type(node: Node<'_, '_>, token: &str) -> bool {
    node.attribute(("http://www.idpf.org/2007/ops", "type"))
        .is_some_and(|value| value.split_whitespace().any(|part| part == token))
}

fn note_kind(node: Node<'_, '_>) -> Option<&'static str> {
    if epub_type(node, "footnote") || node.attribute("role") == Some("doc-footnote") {
        Some("footnote")
    } else if epub_type(node, "endnote") || node.attribute("role") == Some("doc-endnote") {
        Some("endnote")
    } else {
        None
    }
}

fn is_note_reference(node: Node<'_, '_>) -> bool {
    epub_type(node, "noteref") || node.attribute("role") == Some("doc-noteref")
}

struct AssetOwner<'a> {
    member: &'a str,
    document_id: &'a str,
    scope: &'a str,
    scope_id: &'a str,
}

fn push_assets(
    node: Node<'_, '_>,
    key: &str,
    text_offset: usize,
    owner: &AssetOwner<'_>,
    assets: &mut Vec<AssetReference>,
) -> bool {
    let tag = node.tag_name().name();
    let resource = match tag {
        "img" => Some(("image", node.attribute("src").unwrap_or(""), None)),
        "audio" | "video" if node.attribute("src").is_some() => {
            Some((tag, node.attribute("src").unwrap_or(""), None))
        }
        "source" => node
            .parent_element()
            .and_then(|parent| match parent.tag_name().name() {
                "audio" | "video" => Some((
                    parent.tag_name().name(),
                    node.attribute("src").unwrap_or(""),
                    None,
                )),
                _ => None,
            }),
        "track" => Some(("track", node.attribute("src").unwrap_or(""), None)),
        "object" => Some(("object", node.attribute("data").unwrap_or(""), None)),
        "embed" => Some(("embed", node.attribute("src").unwrap_or(""), None)),
        "svg" if node.tag_name().namespace() == Some("http://www.w3.org/2000/svg") => {
            Some(("image", "", Some(node.range().end)))
        }
        "math" if node.tag_name().namespace() == Some("http://www.w3.org/1998/Math/MathML") => {
            Some(("math", "", Some(node.range().end)))
        }
        _ => None,
    };
    let inline_asset = resource.as_ref().is_some_and(|(_, _, end)| end.is_some());
    if let Some((kind, href, source_end)) = resource {
        assets.push(AssetReference {
            document_id: owner.document_id.into(),
            scope: owner.scope.into(),
            scope_id: owner.scope_id.into(),
            kind: kind.into(),
            member: owner.member.into(),
            element_key: key.into(),
            href: href.into(),
            target_member: String::new(),
            media_type: String::new(),
            sha256: String::new(),
            bytes: 0,
            alt: node.attribute("alt").unwrap_or("").into(),
            text_offset,
            source_byte: node.range().start,
            source_end,
        });
    }
    if tag == "video" {
        if let Some(poster) = node.attribute("poster") {
            assets.push(AssetReference {
                document_id: owner.document_id.into(),
                scope: owner.scope.into(),
                scope_id: owner.scope_id.into(),
                kind: "image".into(),
                member: owner.member.into(),
                element_key: key.into(),
                href: poster.into(),
                target_member: String::new(),
                media_type: String::new(),
                sha256: String::new(),
                bytes: 0,
                alt: String::new(),
                text_offset,
                source_byte: node.range().start,
                source_end: None,
            });
        }
    }
    inline_asset
}

struct ReadingProjection<'a> {
    member: &'a str,
    document_id: &'a str,
    text: String,
    elements: Vec<Element>,
    counter: usize,
    notes: &'a mut Vec<NoteBody>,
    references: &'a mut Vec<NoteReference>,
    assets: &'a mut Vec<AssetReference>,
}

fn append_reading(
    node: Node<'_, '_>,
    parent: Option<&str>,
    projection: &mut ReadingProjection<'_>,
) {
    if node.is_text() {
        projection.text.push_str(node.text().unwrap_or(""));
        return;
    }
    if !node.is_element() {
        return;
    }
    if let Some(kind) = note_kind(node) {
        let fragment = node.attribute("id").unwrap_or("").to_owned();
        let source_key = format!("{}#{fragment}", projection.member);
        let mut note_text = String::new();
        let mut note_elements = Vec::new();
        let mut note_counter = 0;
        let owner = AssetOwner {
            member: projection.member,
            document_id: projection.document_id,
            scope: "note",
            scope_id: &source_key,
        };
        append_text(
            node,
            None,
            &mut note_text,
            &mut note_elements,
            &mut note_counter,
            &owner,
            projection.assets,
        );
        projection.notes.push(NoteBody {
            source_key,
            member: projection.member.into(),
            fragment,
            source_byte: node.range().start,
            kind: kind.into(),
            text: note_text,
            elements: note_elements,
        });
        return;
    }
    projection.counter += 1;
    let key = projection.counter.to_string();
    let start = projection.text.chars().count();
    let byte_start = projection.text.len();
    let index = projection.elements.len();
    projection.elements.push(Element {
        key: key.clone(),
        parent: parent.map(str::to_owned),
        tag: node.tag_name().name().into(),
        attributes: node
            .attributes()
            .map(|attr| (attr.name().into(), attr.value().into()))
            .collect(),
        source_byte: node.range().start,
        start,
        end: start,
    });
    let owner = AssetOwner {
        member: projection.member,
        document_id: projection.document_id,
        scope: "document",
        scope_id: projection.document_id,
    };
    let inline_asset = push_assets(node, &key, start, &owner, projection.assets);
    if inline_asset {
        return;
    }
    for nested in node.children() {
        append_reading(nested, Some(&key), projection);
    }
    projection.elements[index].end = projection.text.chars().count();
    if is_note_reference(node) {
        projection.references.push(NoteReference {
            document_id: projection.document_id.into(),
            member: projection.member.into(),
            anchor_key: key,
            href: node.attribute("href").unwrap_or("").into(),
            label: projection.text[byte_start..].into(),
            target_key: String::new(),
            source_byte: node.range().start,
        });
    }
}

fn resolve_note_href(member: &str, href: &str) -> Option<String> {
    let (resource, fragment) = href.split_once('#')?;
    if fragment.is_empty()
        || fragment.contains('#')
        || fragment.contains('%')
        || fragment.chars().any(char::is_whitespace)
    {
        return None;
    }
    let path = if resource.is_empty() {
        member.into()
    } else {
        relative_path(member, resource)?
    };
    Some(format!("{path}#{fragment}"))
}

/// Validate a local EPUB byte snapshot and project its linear XHTML content.
///
/// No archive member is extracted to disk. Limits are checked before expansion.
/// Only UTF-8 XML, unencrypted reflowable XHTML and linear spine content are supported.
/// Referenced footnotes/endnotes use separate text slots; non-linear spine items block.
pub fn validate_epub(bytes: &[u8]) -> EpubReport {
    validate_epub_with_slot_limit(bytes, DEFAULT_MAX_SLOTS)
}

/// Validate with an explicit character-slot bound, capped by `HARD_MAX_SLOTS`.
#[expect(
    clippy::too_many_lines,
    reason = "single pass keeps archive and XML lifetime-bound sources together"
)]
pub fn validate_epub_with_slot_limit(bytes: &[u8], max_slots: usize) -> EpubReport {
    let max_slots = max_slots.min(HARD_MAX_SLOTS);
    let mut result = EpubReport {
        archive_sha256: hash(bytes),
        members: vec![],
        identifier: None,
        metadata: BTreeMap::new(),
        navigation: vec![],
        documents: vec![],
        notes: vec![],
        note_references: vec![],
        images: vec![],
        assets: vec![],
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
            result.finding(
                "<archive>",
                "",
                "EPUB_ZIP",
                "Archive member cannot be opened",
                None,
                true,
            );
            return result;
        };
        let Ok(name) = file.name() else {
            result.finding(
                "<archive>",
                "",
                "EPUB_PATH",
                "Archive member name cannot be decoded",
                None,
                true,
            );
            return result;
        };
        let name = name.into_owned();
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
    let Some(tree) = xml(&mut result, "META-INF/container.xml", container, false) else {
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
    let Some(tree) = xml(&mut result, opf_path, opf, false) else {
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
        let Some(xhtml) = xml(&mut result, path, source, true) else {
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
        if body
            .descendants()
            .any(|n| n.is_element() && matches!(n.tag_name().name(), "script" | "iframe"))
        {
            result.finding(
                path,
                source,
                "EPUB_CONTENT",
                "Embedded, scripted or rich media reading content is unsupported",
                Some(body.range().start),
                true,
            );
        }
        let mut seen_ids = BTreeSet::new();
        for element in body.descendants().filter(Node::is_element) {
            if element.attribute("srcset").is_some() {
                result.finding(
                    path,
                    source,
                    "EPUB_ASSET",
                    "Responsive asset selection is unsupported",
                    Some(element.range().start),
                    true,
                );
            }
            if (element.tag_name().name() == "source"
                && element
                    .parent_element()
                    .is_none_or(|parent| !matches!(parent.tag_name().name(), "audio" | "video")))
                || (element.tag_name().name() == "svg"
                    && element.tag_name().namespace() != Some("http://www.w3.org/2000/svg"))
                || (element.tag_name().name() == "math"
                    && element.tag_name().namespace() != Some("http://www.w3.org/1998/Math/MathML"))
            {
                result.finding(
                    path,
                    source,
                    "EPUB_ASSET",
                    "Asset element has an unsupported context or namespace",
                    Some(element.range().start),
                    true,
                );
            }
            if element.tag_name().namespace() == Some("http://www.w3.org/2000/svg")
                && (matches!(
                    element.tag_name().name(),
                    "script" | "foreignObject" | "image"
                ) || element.attributes().any(|attribute| {
                    attribute.name().starts_with("on")
                        || attribute.value().contains("http:")
                        || attribute.value().contains("https:")
                        || attribute.value().contains("javascript:")
                        || attribute.value().contains("data:")
                }))
            {
                result.finding(
                    path,
                    source,
                    "EPUB_SVG",
                    "Active or externally linked inline SVG is unsupported",
                    Some(element.range().start),
                    true,
                );
            }
            if let Some(id) = element.attribute("id") {
                if !seen_ids.insert(id) {
                    result.finding(
                        path,
                        source,
                        "EPUB_NOTE_ID",
                        "Duplicate XHTML fragment ID",
                        Some(element.range().start),
                        true,
                    );
                }
            }
            if element
                .attribute(("http://www.idpf.org/2007/ops", "type"))
                .is_some_and(|value| {
                    value
                        .split_whitespace()
                        .any(|token| matches!(token, "note" | "rearnote" | "marginalia"))
                })
            {
                result.finding(
                    path,
                    source,
                    "EPUB_NOTE_KIND",
                    "Only footnote and endnote bodies are supported",
                    Some(element.range().start),
                    true,
                );
            }
            if note_kind(element).is_some()
                && element.descendants().skip(1).any(|nested| {
                    nested.is_element()
                        && (note_kind(nested).is_some() || is_note_reference(nested))
                })
            {
                result.finding(
                    path,
                    source,
                    "EPUB_NOTE_NESTED",
                    "Nested notes or note references inside a note are unsupported",
                    Some(element.range().start),
                    true,
                );
            }
        }
        let mut projection = ReadingProjection {
            member: path,
            document_id: idref,
            text: String::new(),
            elements: Vec::new(),
            counter: 0,
            notes: &mut result.notes,
            references: &mut result.note_references,
            assets: &mut result.assets,
        };
        append_reading(body, None, &mut projection);
        result.documents.push(ReadingDocument {
            id: idref.into(),
            member: path.clone(),
            text: projection.text,
            elements: projection.elements,
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
    let mut note_keys = BTreeSet::new();
    let mut note_issues: Vec<(String, usize, &str, &str)> = Vec::new();
    for note in &result.notes {
        if note.fragment.is_empty()
            || note.text.trim().is_empty()
            || !note_keys.insert(note.source_key.clone())
        {
            note_issues.push((
                note.member.clone(),
                note.source_byte,
                "EPUB_NOTE_ID",
                "Note needs a unique fragment ID and nonempty body",
            ));
        }
    }
    for reference in &mut result.note_references {
        reference.target_key =
            resolve_note_href(&reference.member, &reference.href).unwrap_or_default();
    }
    for reference in &result.note_references {
        if reference.label.is_empty() || !note_keys.contains(&reference.target_key) {
            note_issues.push((
                reference.member.clone(),
                reference.source_byte,
                "EPUB_NOTE_REF",
                "Note marker must have text and resolve to one supported note body",
            ));
        }
    }
    let targets: BTreeSet<_> = result
        .note_references
        .iter()
        .map(|reference| reference.target_key.as_str())
        .collect();
    for note in &result.notes {
        if !targets.contains(note.source_key.as_str()) {
            note_issues.push((
                note.member.clone(),
                note.source_byte,
                "EPUB_NOTE_ORPHAN",
                "Note body has no supported reference marker",
            ));
        }
    }
    for (member, byte, code, message) in note_issues {
        if let Some(source) = sources
            .get(&member)
            .and_then(|data| std::str::from_utf8(data).ok())
        {
            result.finding(&member, source, code, message, Some(byte), true);
        }
    }
    let mut asset_issues: Vec<(String, usize, String)> = Vec::new();
    for asset in &mut result.assets {
        let resolved = if let Some(end) = asset.source_end {
            sources
                .get(&asset.member)
                .and_then(|data| data.get(asset.source_byte..end))
                .map(|data| {
                    (
                        asset.member.clone(),
                        if asset.kind == "math" {
                            "application/mathml+xml"
                        } else {
                            "image/svg+xml"
                        }
                        .to_owned(),
                        data,
                    )
                })
        } else {
            relative_path(&asset.member, &asset.href).and_then(|path| {
                items
                    .values()
                    .find(|(item_path, media, _)| {
                        item_path == &path && supported_asset_type(&asset.kind, media)
                    })
                    .and_then(|(_, media, _)| {
                        sources
                            .get(&path)
                            .map(|data| (path.clone(), media.clone(), data.as_slice()))
                    })
            })
        };
        match resolved {
            Some((path, media, data)) if media != "image/svg+xml" || passive_svg(data) => {
                asset.target_member = path;
                asset.media_type = media;
                asset.sha256 = hash(data);
                asset.bytes = data.len();
            }
            _ => asset_issues.push((
                asset.member.clone(),
                asset.source_byte,
                format!("Asset {} must resolve to a safe, manifest-declared resource of the expected type", asset.href),
            )),
        }
    }
    result.images = result
        .assets
        .iter()
        .filter(|asset| asset.kind == "image")
        .cloned()
        .collect();
    for (member, byte, message) in asset_issues {
        if let Some(source) = sources
            .get(&member)
            .and_then(|data| std::str::from_utf8(data).ok())
        {
            result.finding(&member, source, "EPUB_ASSET", &message, Some(byte), true);
        }
    }
    let total_slots = result
        .documents
        .iter()
        .map(|document| document.text.chars().count())
        .sum::<usize>()
        + result
            .notes
            .iter()
            .map(|note| note.text.chars().count())
            .sum::<usize>();
    if total_slots > max_slots {
        result.finding(
            "<archive>",
            "",
            "EPUB_LIMIT",
            &format!("Reading and note projection exceeds {max_slots} character slots"),
            None,
            true,
        );
    }
    result
}
