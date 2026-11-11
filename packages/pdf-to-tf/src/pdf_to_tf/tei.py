"""Build a TEI P5 document from a corpora-pdf extraction.

Every extracted line keeps its exact text in one TEI element with an ``xml:id``
(``p{page}e{index}``) and a ``facs`` pointer to a facsimile zone. Pages become
``pb`` milestones pointing at a ``surface``. The only characters added are
separators between lines and blocks (``\\n``) and between table cells (``\\t``);
OCR word separators are already part of the line text.
"""

import re
import statistics
from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from .issues import Issue, element_id, excerpt, is_page_scan

TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
XML_ID = f"{{{XML_NS}}}id"
XML_LANG = f"{{{XML_NS}}}lang"
ZONE_SCALE = 10  # zone units per Poppler 108-DPI layout unit
HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
PARAGRAPH_GAP = 0.6  # vertical gap, in median line heights, that starts a new paragraph
# whatlang ISO 639-3 codes -> BCP 47 primary subtags; unmapped codes are not guessed.
BCP47 = {
    "ara": "ar", "ces": "cs", "dan": "da", "deu": "de", "ell": "el", "eng": "en",
    "epo": "eo", "fin": "fi", "fra": "fr", "heb": "he", "hun": "hu", "ita": "it",
    "jpn": "ja", "kor": "ko", "lat": "la", "nld": "nl", "nob": "nb", "pol": "pl",
    "por": "pt", "ron": "ro", "rus": "ru", "spa": "es", "swe": "sv", "tur": "tr",
    "ukr": "uk", "cmn": "zh",
}  # fmt: skip
MARK_TAGS = {"link": ("ref", 0), "bold": ("hi", 1), "italic": ("hi", 2)}
INVALID_XML = re.compile("[^\t\n\r\x20-퟿-�\U00010000-\U0010ffff]")


def tei(tag: str) -> str:
    return f"{{{TEI_NS}}}{tag}"


@dataclass
class Mapped:
    """Where one extracted element went."""

    page: int
    index: int
    kind: str
    xml_id: str
    status: str  # projected | zero-width | omitted
    tei_tag: str | None = None
    text: str = ""
    zone: tuple[int, int, int, int] | None = None
    words: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TeiBuild:
    xml: bytes
    elements: list[Mapped]
    issues: list[Issue]
    languages: list[str]


def zone_of(bounds: dict[str, float]) -> tuple[int, int, int, int]:
    x, y = bounds["x"], bounds["y"]
    return (
        round(x * ZONE_SCALE),
        round(y * ZONE_SCALE),
        round((x + bounds["width"]) * ZONE_SCALE),
        round((y + bounds["height"]) * ZONE_SCALE),
    )


def sub(parent: etree._Element, tag: str, attrib: dict[str, str] | None = None) -> etree._Element:
    return etree.SubElement(parent, tei(tag), attrib or {})


def append_text(parent: etree._Element, value: str) -> None:
    if not value:
        return
    if len(parent):
        last = parent[-1]
        last.tail = (last.tail or "") + value
    else:
        parent.text = (parent.text or "") + value


def bcp47(page: dict[str, Any]) -> str | None:
    code = page.get("language")
    return BCP47.get(code) if code and page.get("language_reliable") else None


class Builder:
    def __init__(self, extraction: dict[str, Any], title: str, tools: dict[str, str]) -> None:
        self.extraction = extraction
        self.title = title
        self.tools = tools
        self.mapped: list[Mapped] = []
        self.issues: list[Issue] = []
        self.languages: set[str] = set()

    # -- text helpers --------------------------------------------------------
    def clean(self, text: str, page: int, index: int, word: int | None = None) -> str:
        bad = sorted({f"U+{ord(c):04X}" for c in INVALID_XML.findall(text)})
        if not bad:
            return text
        self.issues.append(
            Issue(
                "xml_incompatible_character",
                "characters " + ", ".join(bad) + " replaced by U+FFFD",
                page,
                index,
                word,
                text=excerpt(text),
                xml_id=element_id(page, index, word),
            )
        )
        return INVALID_XML.sub("�", text)

    def mark_spans(
        self, text: str, marks: list[dict[str, Any]], page: int, index: int
    ) -> list[tuple[int, int, int, dict[str, Any]]]:
        spans: list[tuple[int, int, int, dict[str, Any]]] = []
        used: set[tuple[str, int]] = set()
        for mark in marks:
            needle = mark.get("text") or ""
            if not needle.strip() or mark.get("kind") not in MARK_TAGS:
                continue
            start = text.find(needle)
            while start != -1 and (mark["kind"], start) in used:
                start = text.find(needle, start + 1)
            if start == -1:
                self.issues.append(
                    Issue(
                        "mark_not_located",
                        f"{mark['kind']} text {excerpt(needle, 40)!r} not found in line",
                        page,
                        index,
                        text=excerpt(text),
                        xml_id=element_id(page, index),
                    )
                )
                continue
            used.add((mark["kind"], start))
            end = start + len(needle)
            if any(s < start < e < end or start < s < end < e for s, e, _, _ in spans):
                self.issues.append(
                    Issue(
                        "mark_overlap_dropped",
                        f"{mark['kind']} {excerpt(needle, 40)!r} crosses another mark",
                        page,
                        index,
                        text=excerpt(text),
                        xml_id=element_id(page, index),
                    )
                )
                continue
            spans.append((start, end, MARK_TAGS[mark["kind"]][1], mark))
        spans.sort(key=lambda s: (s[0], -s[1], s[2]))
        return spans

    def render(
        self,
        parent: etree._Element,
        text: str,
        spans: list[tuple[int, int, int, dict[str, Any]]],
        offset: int,
    ) -> None:
        position = offset
        index = 0
        while index < len(spans):
            start, end, _, mark = spans[index]
            inner = []
            index += 1
            while index < len(spans) and spans[index][1] <= end:
                inner.append(spans[index])
                index += 1
            append_text(parent, text[position - offset : start - offset])
            tag = MARK_TAGS[mark["kind"]][0]
            attrib = {"rend": mark["kind"]} if tag == "hi" else {}
            if tag == "ref" and mark.get("target"):
                attrib["target"] = mark["target"]
            child = sub(parent, tag, attrib)
            self.render(child, text[start - offset : end - offset], inner, start)
            position = end
        append_text(parent, text[position - offset :])

    # -- element filling -----------------------------------------------------
    def fill(
        self,
        target: etree._Element,
        surface: etree._Element,
        page: dict[str, Any],
        index: int,
        element: dict[str, Any],
    ) -> None:
        number = page["number"]
        ident = element_id(number, index)
        zone = zone_of(element["bounds"])
        self.add_zone(surface, ident, zone)
        target.set(XML_ID, ident)
        target.set("facs", f"#z-{ident}")
        lang = bcp47(page)
        if lang:
            target.set(XML_LANG, lang)
            self.languages.add(lang)
        text = self.clean(element["text"], number, index)
        words = element.get("words") or []
        mapped = Mapped(number, index, element["kind"], ident, "projected", None, text, zone)
        if words and " ".join(w["text"] for w in words) == element["text"]:
            for word_index, word in enumerate(words):
                wid = element_id(number, index, word_index)
                wzone = zone_of(word["bounds"])
                self.add_zone(surface, wid, wzone)
                w = sub(
                    target,
                    "w",
                    {XML_ID: wid, "facs": f"#z-{wid}", "cert": f"{word['confidence']:.3f}"},
                )
                w.text = self.clean(word["text"], number, index, word_index)
                if word_index + 1 < len(words):
                    w.tail = " "
                mapped.words.append(
                    {"xml_id": wid, "text": w.text, "zone": wzone, "cert": w.get("cert")}
                )
        else:
            if words:
                self.issues.append(
                    Issue(
                        "words_text_mismatch",
                        "joined OCR words differ from the line text",
                        number,
                        index,
                        text=excerpt(element["text"]),
                        xml_id=ident,
                    )
                )
            spans = self.mark_spans(text, element.get("marks") or [], number, index)
            self.render(target, text, spans, 0)
        mapped.tei_tag = etree.QName(target).localname
        self.mapped.append(mapped)

    def add_zone(
        self, surface: etree._Element, ident: str, zone: tuple[int, int, int, int]
    ) -> None:
        ulx, uly, lrx, lry = zone
        sub(
            surface,
            "zone",
            {
                XML_ID: f"z-{ident}",
                "ulx": str(ulx),
                "uly": str(uly),
                "lrx": str(lrx),
                "lry": str(lry),
            },
        )

    # -- grouping ------------------------------------------------------------
    @staticmethod
    def groups(page: dict[str, Any]) -> list[tuple[str, list[tuple[int, dict[str, Any]]]]]:
        elements = list(enumerate(page["elements"]))
        heights = [e["bounds"]["height"] for _, e in elements if e["kind"] == "paragraph"]
        line = statistics.median(heights) if heights else 0.0
        out: list[tuple[str, list[tuple[int, dict[str, Any]]]]] = []
        for index, element in elements:
            kind = element["kind"]
            key = f"table:{element.get('table_id')}" if kind == "table_cell" else kind
            previous = out[-1] if out else None
            if (
                previous
                and previous[0] == key
                and kind
                in {
                    "paragraph",
                    "list_item",
                    "reference",
                    "table_cell",
                }
            ):
                if kind == "paragraph":
                    last = previous[1][-1][1]["bounds"]
                    here = element["bounds"]
                    gap = here["y"] - (last["y"] + last["height"])
                    if here["y"] < last["y"] or gap > PARAGRAPH_GAP * line:
                        out.append((key, [(index, element)]))
                        continue
                previous[1].append((index, element))
            else:
                out.append((key, [(index, element)]))
        return out

    # -- document ------------------------------------------------------------
    def header(self, root: etree._Element) -> None:
        extraction = self.extraction
        header = sub(root, "teiHeader")
        file_desc = sub(header, "fileDesc")
        sub(sub(file_desc, "titleStmt"), "title").text = self.title
        sub(
            sub(file_desc, "publicationStmt"), "p"
        ).text = "Machine conversion by corpora pdf-to-tf; not a published edition."
        bibl = sub(sub(file_desc, "sourceDesc"), "bibl")
        sub(bibl, "title").text = self.title
        sub(bibl, "idno", {"type": "sha256"}).text = extraction["source_sha256"]
        sub(bibl, "extent").text = f"{len(extraction['pages'])} pages"
        encoding = sub(header, "encodingDesc")
        app_info = sub(encoding, "appInfo")
        for ident, version in sorted(self.tools.items()):
            app = sub(app_info, "application", {"ident": ident, "version": version or "unknown"})
            sub(app, "label").text = ident
        decl = sub(encoding, "editorialDecl")
        for text in (
            "Text is the unmodified engine output; characters XML 1.0 cannot store are "
            "replaced by U+FFFD and reported.",
            "Each extracted line is one element with xml:id p{page}e{index}; OCR words are "
            "w elements p{page}e{index}w{word} with @cert = OCR word confidence.",
            "Added separators only: newline between lines and blocks, tab between table cells.",
            "Headings, lists, references, citations, tables and paragraph grouping are "
            "layout heuristics from corpora-pdf, not source PDF tags.",
            f"Facsimile coordinates are integer tenths of Poppler 108-DPI layout units "
            f"(scale {ZONE_SCALE}), origin top-left of the rendered MediaBox.",
        ):
            sub(decl, "p").text = text

    def build(self) -> TeiBuild:
        root = etree.Element(tei("TEI"), nsmap={None: TEI_NS})  # type: ignore[dict-item]
        self.header(root)
        facsimile = sub(root, "facsimile")
        body = sub(sub(root, "text"), "body")
        stack: list[tuple[int, etree._Element]] = []

        def container() -> etree._Element:
            return stack[-1][1] if stack else body

        for page in self.extraction["pages"]:
            number = page["number"]
            width = round(page["width"] * ZONE_SCALE)
            height = round(page["height"] * ZONE_SCALE)
            surface = sub(
                facsimile,
                "surface",
                {XML_ID: f"p{number}", "n": str(number), "ulx": "0", "uly": "0",
                 "lrx": str(width), "lry": str(height)},
            )  # fmt: skip
            sub(container(), "pb", {"n": str(number), "facs": f"#p{number}"})
            for key, members in self.groups(page):
                self.block(key, members, page, surface, container, stack)
        languages = sorted(self.languages)
        if languages:
            usage = sub(sub(root[0], "profileDesc"), "langUsage")
            for lang in languages:
                sub(usage, "language", {"ident": lang}).text = lang
        xml = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
        return TeiBuild(xml, self.mapped, self.issues, languages)

    def block(
        self,
        key: str,
        members: list[tuple[int, dict[str, Any]]],
        page: dict[str, Any],
        surface: etree._Element,
        container: Any,
        stack: list[tuple[int, etree._Element]],
    ) -> None:
        number = page["number"]
        kind = members[0][1]["kind"]
        visual = kind in {"image", "graph_candidate"}
        texted = [(i, e) for i, e in members if visual or e["text"].strip()]
        kept = {i for i, _ in texted}
        for index, element in members:
            if index not in kept:
                self.mapped.append(
                    Mapped(number, index, kind, element_id(number, index), "omitted")
                )
                self.issues.append(
                    Issue(
                        "whitespace_element_omitted",
                        "whitespace-only line",
                        number,
                        index,
                        bounds=element["bounds"],
                        xml_id=element_id(number, index),
                    )
                )
        if not texted:
            return
        if kind in HEADINGS:
            level = HEADINGS[kind]
            while stack and stack[-1][0] >= level:
                stack.pop()
            div = sub(container(), "div", {"type": "section"})
            stack.append((level, div))
            for index, element in texted:
                head = sub(div, "head", {"type": kind})
                self.fill(head, surface, page, index, element)
                head.tail = "\n"
            return
        parent = container()
        if kind in {"image", "graph_candidate"}:
            for index, element in texted:
                ident = element_id(number, index)
                zone = zone_of(element["bounds"])
                self.add_zone(surface, ident, zone)
                figure_type = "page-scan" if is_page_scan(page, element) else kind.replace("_", "-")
                sub(parent, "figure", {XML_ID: ident, "facs": f"#z-{ident}", "type": figure_type})
                self.mapped.append(
                    Mapped(number, index, kind, ident, "zero-width", "figure", "", zone)
                )
                if figure_type != "page-scan":
                    self.issues.append(
                        Issue("visual_not_in_tf", f"{kind} has no text", number, index,
                              bounds=element["bounds"], xml_id=ident)
                    )  # fmt: skip
            return
        if kind.startswith("table"):
            table = sub(parent, "table")
            row: etree._Element | None = None
            top = height = 0.0
            for index, element in texted:
                b = element["bounds"]
                if row is None or b["y"] >= top + 0.5 * height:
                    if row is not None:
                        row.tail = "\n"
                    row = sub(table, "row")
                    top, height = b["y"], b["height"]
                elif len(row):
                    row[-1].tail = "\t"
                cell = sub(row, "cell")
                self.fill(cell, surface, page, index, element)
            table.tail = "\n"
            first = texted[0]
            self.issues.append(
                Issue("table_structure_heuristic", f"table of {len(texted)} cells", number,
                      first[0], bounds=first[1]["bounds"], xml_id=element_id(number, first[0]))
            )  # fmt: skip
            return
        wrappers = {
            "paragraph": ("p", "seg", {"type": "line"}),
            "list_item": ("list", "item", {}),
            "reference": ("listBibl", "bibl", {}),
        }
        if kind in wrappers:
            outer_tag, inner_tag, attrib = wrappers[kind]
            outer = sub(parent, outer_tag)
            for position, (index, element) in enumerate(texted):
                inner = sub(outer, inner_tag, dict(attrib))
                self.fill(inner, surface, page, index, element)
                if position + 1 < len(texted):
                    inner.tail = "\n"
            outer.tail = "\n"
            return
        for index, element in texted:  # citation and any future kind: one ab per line
            ab = sub(parent, "ab", {"type": kind.replace("_", "-")})
            self.fill(ab, surface, page, index, element)
            ab.tail = "\n"


def build_tei(extraction: dict[str, Any], title: str, tools: dict[str, str]) -> TeiBuild:
    return Builder(extraction, title, tools).build()
