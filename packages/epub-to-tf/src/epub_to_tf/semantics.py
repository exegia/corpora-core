"""Source-declared XHTML roles, links, and publication navigation."""

import posixpath
from collections import defaultdict
from typing import Any
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

from lxml import etree

EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _target(member: str, href: str) -> tuple[str | None, str | None, bool]:
    parsed = urlsplit(href)
    if parsed.scheme or parsed.netloc:
        return None, None, True
    path = (
        posixpath.normpath(posixpath.join(posixpath.dirname(member), unquote(parsed.path)))
        if parsed.path
        else member
    )
    if path == ".." or path.startswith("../") or path.startswith("/"):
        return None, None, False
    return path, unquote(parsed.fragment) or None, False


def _entry(
    source_member: str,
    label: str,
    href: str,
    parent: int | None,
    level: int,
    source_line: int | None,
    members: set[str],
) -> dict[str, Any]:
    target_member, fragment, external = _target(source_member, href)
    if external or target_member not in members:
        raise ValueError(
            f"{source_member}:{source_line}: TOC target is missing or external: {href}"
        )
    return {
        "source_member": source_member,
        "source_line": source_line,
        "label": " ".join(label.split()),
        "raw_label": label,
        "href": href,
        "target_member": target_member,
        "fragment": fragment,
        "parent": parent,
        "level": level,
    }


def _walk_html_list(
    list_node: Any,
    parent: int | None,
    level: int,
    source_member: str,
    members: set[str],
    entries: list[dict[str, Any]],
) -> None:
    for li in list_node:
        if not isinstance(li.tag, str) or _local(li.tag) != "li":
            continue
        link = next(
            (child for child in li if isinstance(child.tag, str) and _local(child.tag) == "a"),
            None,
        )
        index = parent
        if link is not None and link.get("href"):
            index = len(entries)
            entries.append(
                _entry(
                    source_member,
                    "".join(link.itertext()),
                    link.get("href"),
                    parent,
                    level,
                    link.sourceline,
                    members,
                )
            )
        for child in li:
            if isinstance(child.tag, str) and _local(child.tag) in {"ol", "ul"}:
                _walk_html_list(child, index, level + 1, source_member, members, entries)


def _walk_ncx_point(
    point: Any,
    parent: int | None,
    level: int,
    source_member: str,
    members: set[str],
    entries: list[dict[str, Any]],
) -> None:
    label_node = next(
        (n for n in point.iter() if isinstance(n.tag, str) and _local(n.tag) == "text"),
        None,
    )
    content = next(
        (n for n in point if isinstance(n.tag, str) and _local(n.tag) == "content"),
        None,
    )
    index = parent
    if content is not None and content.get("src"):
        index = len(entries)
        entries.append(
            _entry(
                source_member,
                "".join(label_node.itertext()) if label_node is not None else "",
                content.get("src"),
                parent,
                level,
                point.sourceline,
                members,
            )
        )
    for child in point:
        if isinstance(child.tag, str) and _local(child.tag) == "navPoint":
            _walk_ncx_point(child, index, level + 1, source_member, members, entries)


def _validate_fragments(
    entries: list[dict[str, Any]], archive: ZipFile, parser: Any
) -> list[dict[str, Any]]:
    ids: dict[str, set[str]] = {}
    for entry in entries:
        fragment = entry["fragment"]
        if fragment is None:
            continue
        member = entry["target_member"]
        if member not in ids:
            try:
                root = etree.fromstring(archive.read(member), parser)
            except etree.XMLSyntaxError as error:
                raise ValueError(f"{member}: cannot inspect TOC fragment: {error}") from error
            ids[member] = {
                node.get("id")
                for node in root.iter()
                if isinstance(node.tag, str) and node.get("id")
            }
        if fragment not in ids[member]:
            raise ValueError(
                f"{entry['source_member']}:{entry['source_line']}: "
                f"TOC fragment is missing: {entry['href']}"
            )
    return entries


def extract_toc(archive: ZipFile, navigation: list[str]) -> list[dict[str, Any]]:
    """Prefer EPUB3 toc nav; fall back to NCX, retaining hierarchy and targets."""
    members = set(archive.namelist())
    parser = etree.XMLParser(recover=False, no_network=True, load_dtd=False, resolve_entities=False)
    for source_member in navigation:
        if not source_member.lower().endswith((".xhtml", ".html")):
            continue
        try:
            root = etree.fromstring(archive.read(source_member), parser)
        except etree.XMLSyntaxError as error:
            raise ValueError(f"{source_member}: malformed EPUB navigation: {error}") from error
        toc_nav = next(
            (
                node
                for node in root.iter()
                if isinstance(node.tag, str)
                and _local(node.tag) == "nav"
                and ("toc" in node.get(EPUB_TYPE, "").split() or node.get("role") == "doc-toc")
            ),
            None,
        )
        if toc_nav is None:
            continue
        entries: list[dict[str, Any]] = []
        for child in toc_nav.iter():
            if (
                isinstance(child.tag, str)
                and _local(child.tag) in {"ol", "ul"}
                and not any(
                    isinstance(ancestor.tag, str) and _local(ancestor.tag) in {"ol", "ul"}
                    for ancestor in child.iterancestors()
                )
            ):
                _walk_html_list(child, None, 1, source_member, members, entries)
        if entries:
            return _validate_fragments(entries, archive, parser)
    for source_member in navigation:
        if not source_member.lower().endswith(".ncx"):
            continue
        try:
            root = etree.fromstring(archive.read(source_member), parser)
        except etree.XMLSyntaxError as error:
            raise ValueError(f"{source_member}: malformed NCX: {error}") from error
        nav_map = next(
            (n for n in root.iter() if isinstance(n.tag, str) and _local(n.tag) == "navMap"),
            None,
        )
        if nav_map is None:
            continue
        entries = []
        for point in nav_map:
            if isinstance(point.tag, str) and _local(point.tag) == "navPoint":
                _walk_ncx_point(point, None, 1, source_member, members, entries)
        return _validate_fragments(entries, archive, parser)
    return []


def annotate_document(document: dict[str, Any], members: set[str]) -> list[dict[str, Any]]:
    """Tag only roles supported by explicit XHTML tags, classes, or EPUB roles."""
    lookup = {element["key"]: element for element in document["elements"]}
    links: list[dict[str, Any]] = []

    def in_navigation(element: dict[str, Any]) -> bool:
        current: dict[str, Any] | None = element
        while current is not None:
            attributes = current["attributes"]
            classes = set(attributes.get("class", "").split())
            if (
                current["tag"] == "nav"
                or classes & {"toc", "chaptersMenu", "returnToMenu"}
                or "toc" in attributes.get("type", "").split()
                or attributes.get("role") == "doc-toc"
            ):
                return True
            current = lookup.get(current["parent"])
        return False

    for element in document["elements"]:
        tag = element["tag"]
        attributes = element["attributes"]
        classes = set(attributes.get("class", "").split())
        start, end = element["reading_start"], element["reading_end"]
        label = document["reading_text"][start:end].strip()
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            element["semantic_kind"] = (
                "subtitle"
                if (
                    "subtitle" in attributes.get("type", "").split()
                    or "chapter-subtitle" in classes
                    or attributes.get("role") == "doc-subtitle"
                )
                else "heading"
            )
            element["heading_level"] = int(tag[1])
            element["semantic_label"] = label
        elif (tag == "sup" and "v" in classes) or "verse-number" in classes:
            element["semantic_kind"] = "verse_number"
            element["verse_number"] = label
        elif tag == "table":
            element["semantic_kind"] = "table"
        elif tag == "nav" or "toc" in classes and tag in {"section", "div"}:
            element["semantic_kind"] = "toc" if "toc" in classes else "navigation"
        if tag != "a" or not attributes.get("href"):
            continue
        href = attributes["href"]
        kind = (
            "note"
            if "noteref" in attributes.get("type", "").split()
            or attributes.get("role") == "doc-noteref"
            else "navigation"
            if in_navigation(element)
            else "reference"
        )
        target_member, fragment, external = _target(document["member"], href)
        element["semantic_kind"] = kind + "_link"
        element["link_kind"] = kind
        element["link_href"] = href
        element["link_target_member"] = target_member or ""
        element["link_fragment"] = fragment or ""
        element["link_external"] = int(external)
        links.append(
            {
                "source_member": document["member"],
                "source_byte": element["source_byte"],
                "element_key": element["key"],
                "kind": kind,
                "label": label,
                "href": href,
                "target_member": target_member,
                "fragment": fragment,
                "external": external,
                "target_exists": target_member in members if target_member else None,
            }
        )
    return links


def toc_by_member(toc: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for index, entry in enumerate(toc):
        grouped[entry["target_member"]].append({"index": index, **entry})
    return grouped
