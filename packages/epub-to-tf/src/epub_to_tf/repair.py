"""Guarded XHTML repair candidates; the Rust validator remains the authority."""

import hashlib
import posixpath
from collections import Counter, defaultdict
from html.parser import HTMLParser
from io import BytesIO
from typing import Any
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from lxml import etree

XHTML = "http://www.w3.org/1999/xhtml"
EPUB = "http://www.idpf.org/2007/ops"
XML = "http://www.w3.org/XML/1998/namespace"


class RepairRejected(ValueError):
    """A proposed repair cannot be proven text faithful and unambiguous."""


class SourceBody(HTMLParser):
    """Independent lexical text and explicit tag inventory for a source body."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_body = False
        self.seen_body = False
        self.text: list[str] = []
        self.after_body: list[str] = []
        self.tags: Counter[str] = Counter()
        self.attributes: Counter[tuple[str, str, str | None]] = Counter()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags[tag] += 1
        self.attributes.update((tag, name, value) for name, value in attrs)
        if tag == "body":
            self.seen_body = True
            self.in_body = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "body":
            self.in_body = False

    def handle_data(self, data: str) -> None:
        if self.in_body:
            self.text.append(data)
        elif self.seen_body:
            self.after_body.append(data)


def _strict(data: bytes) -> etree._Element:
    return etree.fromstring(
        data,
        etree.XMLParser(recover=False, no_network=True, load_dtd=False, resolve_entities=False),
    )


def _copy_element(source: etree._Element, changes: list[dict[str, str]]) -> etree._Element:
    if not isinstance(source.tag, str):
        if source.tag is etree.Comment:
            comment = etree.Comment(source.text or "")
            comment.tail = source.tail
            return comment
        raise RepairRejected("Unsupported XHTML node in recovered tree")
    if ":" in source.tag or source.tag in {"script", "iframe", "svg", "math"}:
        raise RepairRejected(f"Unsupported recovered element: {source.tag}")
    target = etree.Element(f"{{{XHTML}}}{source.tag}")
    for name, value in source.attrib.items():
        if name in {"xmlns", "xmlns:epub", "xmlns:xml"}:
            continue
        if name == "epub:type":
            target.set(f"{{{EPUB}}}type", value)
        elif name == "xml:lang":
            target.set(f"{{{XML}}}lang", value)
        elif (
            ":" in name
            or not name
            or not (name[0].isalpha() or name[0] == "_")
            or any(not (char.isalnum() or char in "._-") for char in name)
        ):
            key = f"data-source-attr-{len(changes) + 1}"
            target.set(key, f"{name}={value}")
            changes.append({"attribute": name, "value": value, "mapped_to": key})
        else:
            target.set(name, value)
    target.text = source.text
    for child in source:
        target.append(_copy_element(child, changes))
    target.tail = source.tail
    return target


def _recover_xhtml(member: str, data: bytes) -> tuple[bytes, dict[str, Any]]:
    if b"<!ENTITY" in data.upper() or b"<![CDATA[" in data.upper():
        raise RepairRejected(f"{member}: entity declarations or CDATA need manual review")
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RepairRejected(f"{member}: XHTML is not UTF-8") from error
    source = SourceBody()
    source.feed(decoded)
    source.close()
    if not source.seen_body or any(text.strip() for text in source.after_body):
        raise RepairRejected(f"{member}: missing body or non-whitespace text after body")
    parser = etree.HTMLParser(recover=True, no_network=True, huge_tree=False, encoding="utf-8")
    try:
        recovered = etree.fromstring(data, parser)
    except (etree.XMLSyntaxError, ValueError) as error:
        raise RepairRejected(f"{member}: HTML recovery parser rejected source: {error}") from error
    body = recovered.find("body")
    if body is None:
        raise RepairRejected(f"{member}: recovery found no body")
    recovered_tags = Counter(node.tag for node in recovered.iter() if isinstance(node.tag, str))
    lost = {
        tag: count - recovered_tags[tag]
        for tag, count in source.tags.items()
        if count > recovered_tags[tag]
    }
    if lost:
        raise RepairRejected(f"{member}: recovery lost explicit elements: {lost}")
    recovered_attributes = Counter(
        (node.tag, name, value)
        for node in recovered.iter()
        if isinstance(node.tag, str)
        for name, value in node.attrib.items()
    )
    lost_attributes = source.attributes - recovered_attributes
    if lost_attributes:
        raise RepairRejected(f"{member}: recovery lost source attributes")
    lexical_text = "".join(source.text)
    if "".join(body.itertext()) != lexical_text:
        raise RepairRejected(f"{member}: recovery changed body text")
    changes: list[dict[str, str]] = []
    candidate = _copy_element(recovered, changes)
    candidate_bytes = etree.tostring(candidate, encoding="utf-8", xml_declaration=True)
    try:
        strict = _strict(candidate_bytes)
    except etree.XMLSyntaxError as error:
        raise RepairRejected(
            f"{member}: repaired candidate is not strict XHTML: {error}"
        ) from error
    strict_body = strict.find(f"{{{XHTML}}}body")
    if strict_body is None or "".join(strict_body.itertext()) != lexical_text:
        raise RepairRejected(f"{member}: strict candidate changed body text")
    return candidate_bytes, {
        "member": member,
        "action": "recover_xhtml",
        "original_sha256": hashlib.sha256(data).hexdigest(),
        "candidate_sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "body_chars": len(lexical_text),
        "explicit_start_tags": sum(source.tags.values()),
        "explicit_attributes": sum(source.attributes.values()),
        "parser_findings": [str(error) for error in parser.error_log],
        "attribute_mappings": changes,
    }


def _references(chapters: dict[str, bytes]) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    for member, data in chapters.items():
        try:
            root = _strict(data)
        except etree.XMLSyntaxError as error:
            raise RepairRejected(f"{member}: cannot inspect references: {error}") from error
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            for name in ("href", "src"):
                value = node.get(name)
                if not value:
                    continue
                parsed = urlsplit(value)
                if parsed.scheme or parsed.netloc or not parsed.fragment:
                    continue
                target = (
                    posixpath.normpath(
                        posixpath.join(posixpath.dirname(member), unquote(parsed.path))
                    )
                    if parsed.path
                    else member
                )
                refs.add((target, unquote(parsed.fragment)))
    return refs


def repair_archive(original: bytes, report: dict[str, Any]) -> tuple[bytes, list[dict[str, Any]]]:
    """Repair only malformed XHTML and unreferenced duplicate IDs, with a ledger."""
    problems = defaultdict(set)
    for item in report["findings"]:
        for diagnostic in item["report"]["diagnostics"]:
            if diagnostic["blocking"]:
                problems[item["member"]].add(diagnostic["code"])
    allowed = {"EPUB_XML", "EPUB_NOTE_ID", "EPUB_LIMIT", "EPUB_SPINE"}
    if any(code not in allowed for codes in problems.values() for code in codes):
        raise RepairRejected("EPUB has blockers outside the supported repair policy")
    if "EPUB_SPINE" in {code for codes in problems.values() for code in codes}:
        spine_messages = [
            diagnostic["message"]
            for item in report["findings"]
            for diagnostic in item["report"]["diagnostics"]
            if diagnostic["code"] == "EPUB_SPINE"
        ]
        if spine_messages != ["No supported linear reading content"] or not any(
            "EPUB_XML" in codes for codes in problems.values()
        ):
            raise RepairRejected("Spine failure is not a consequence of malformed XHTML")
    if problems.get("<archive>", set()) - {"EPUB_LIMIT"}:
        raise RepairRejected("EPUB archive has unsupported blockers")
    replacements: dict[str, bytes] = {}
    ledger: list[dict[str, Any]] = []
    with ZipFile(BytesIO(original)) as source:
        names = set(source.namelist())
        for member, codes in problems.items():
            if "EPUB_XML" in codes:
                if member not in names or not member.lower().endswith(".xhtml"):
                    raise RepairRejected(f"Cannot repair non-XHTML member: {member}")
                candidate, record = _recover_xhtml(member, source.read(member))
                replacements[member] = candidate
                ledger.append(record)
        # Parse every XHTML member before an identity edit; ambiguous inbound links block.
        chapters = {
            name: replacements.get(name, source.read(name))
            for name in sorted(names)
            if name.lower().endswith((".xhtml", ".html", ".htm"))
        }
        ncx = {name: source.read(name) for name in sorted(names) if name.lower().endswith(".ncx")}
        references = _references({**chapters, **ncx})
        editable = {document["member"] for document in report["documents"]} | {
            member for member, codes in problems.items() if "EPUB_XML" in codes
        }
        for member in sorted(editable):
            try:
                root = _strict(chapters[member])
            except etree.XMLSyntaxError as error:
                raise RepairRejected(f"{member}: cannot inspect fragment IDs: {error}") from error
            body = root.find(f"{{{XHTML}}}body")
            if body is None:
                raise RepairRejected(f"{member}: repaired XHTML has no body")
            counts = Counter(node.get("id") for node in body.iter() if node.get("id"))
            duplicates = {value for value, count in counts.items() if count > 1}
            if not duplicates:
                continue
            if any((member, value) in references for value in duplicates):
                raise RepairRejected(f"{member}: duplicate ID has an inbound reference")
            seen: Counter[str] = Counter()
            edits = []
            occupied = set(counts)
            for node in body.iter():
                value = node.get("id")
                if value not in duplicates:
                    continue
                seen[value] += 1
                if seen[value] == 1:
                    continue
                suffix = seen[value]
                renamed = f"{value}--tf-recovered-{suffix}"
                while renamed in occupied:
                    suffix += 1
                    renamed = f"{value}--tf-recovered-{suffix}"
                occupied.add(renamed)
                node.set("id", renamed)
                edits.append({"original": value, "candidate": renamed})
            candidate = etree.tostring(root, encoding="utf-8", xml_declaration=True)
            try:
                _strict(candidate)
            except etree.XMLSyntaxError as error:
                raise RepairRejected(f"{member}: ID repair made invalid XHTML: {error}") from error
            replacements[member] = candidate
            ledger.append(
                {
                    "member": member,
                    "action": "disambiguate_unreferenced_ids",
                    "original_sha256": hashlib.sha256(chapters[member]).hexdigest(),
                    "candidate_sha256": hashlib.sha256(candidate).hexdigest(),
                    "edits": edits,
                }
            )
        target = BytesIO()
        with ZipFile(target, "w") as archive:
            for info in source.infolist():
                archive.writestr(info, replacements.get(info.filename, source.read(info.filename)))
    return target.getvalue(), ledger
