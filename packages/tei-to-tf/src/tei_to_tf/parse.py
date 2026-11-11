"""Namespace-aware TEI projection with explicit editorial decisions."""

import hashlib
import io
import re
from collections import Counter
from typing import Any, cast

from lxml import etree

from .model import ConversionError, Document, Element, Policy, Region, Source

TEI = "http://www.tei-c.org/ns/1.0"
XML = "http://www.w3.org/XML/1998/namespace"
XINCLUDE = "http://www.w3.org/2001/XInclude"
TOC_TYPES = {"toc", "contents", "tableofcontents", "table-of-contents"}


def qname(element: etree._Element) -> tuple[str, str]:
    if not isinstance(element.tag, str):
        return "", ""
    name = etree.QName(element)
    return name.namespace or "", name.localname


def secure_tree(data: bytes) -> etree._ElementTree:
    parser = etree.XMLParser(
        resolve_entities=False,
        load_dtd=False,
        no_network=True,
        remove_blank_text=False,
        remove_comments=False,
        huge_tree=False,
    )
    try:
        tree = etree.parse(io.BytesIO(data), parser)
    except etree.XMLSyntaxError as exc:
        raise ConversionError(f"Malformed XML: {exc}") from exc
    if getattr(tree.docinfo, "doctype", ""):
        raise ConversionError("DTD declarations are unsupported; supply self-contained XML")
    if any(isinstance(node, etree._Entity) for node in tree.iter()):
        raise ConversionError("Unresolved XML entities are unsupported")
    return tree


def fragment(node: etree._Element) -> str:
    return etree.tostring(node, encoding="unicode", with_tail=False)


def metadata(node: etree._Element, namespace: str) -> dict[str, Any]:
    ns = {"t": namespace} if namespace else {}

    def select(path: str) -> list[etree._Element]:
        expression = "/".join(f"t:{part}" if namespace else part for part in path.split("/"))
        return list(node.findall(expression, ns))

    def texts(path: str) -> list[str]:
        return [
            "".join(t.decode("utf-8") if isinstance(t, bytes) else t for t in x.itertext()).strip()
            for x in select(path)
        ]

    headers = select("teiHeader")
    return {
        "attributes": {str(k): str(v) for k, v in node.attrib.items()},
        "titles": texts("teiHeader/fileDesc/titleStmt/title"),
        "authors": texts("teiHeader/fileDesc/titleStmt/author"),
        "publishers": texts("teiHeader/fileDesc/publicationStmt/publisher"),
        "publication_dates": texts("teiHeader/fileDesc/publicationStmt/date"),
        "headers": [fragment(x) for x in headers],
    }


ZONE_COORDINATES = ("ulx", "uly", "lrx", "lry")


def facsimile_zones(member: etree._Element, namespace: str) -> dict[str, dict[str, str]]:
    """Map xml:id of each facsimile surface/zone to its surface number and raw coordinates.

    Only direct `facsimile/surface[/zone]` children of this TEI member are read; values stay
    strings here so the exporter can reject non-integer coordinates instead of rounding them.
    """
    zones: dict[str, dict[str, str]] = {}
    for facsimile in member:
        if qname(facsimile) != (namespace, "facsimile"):
            continue
        for surface in facsimile:
            if qname(surface) != (namespace, "surface"):
                continue
            label = surface.get("n", "")
            for node in [surface, *(z for z in surface if qname(z) == (namespace, "zone"))]:
                identity = node.get(f"{{{XML}}}id")
                if identity:
                    zones[identity] = {"surface": label} | {
                        key: node.get(key, "") for key in ZONE_COORDINATES
                    }
    return zones


def parse(source: Source, policy: Policy) -> tuple[list[Document], dict[str, Any]]:
    """Separate metadata from selected reading text, retaining original bytes elsewhere."""
    tree = secure_tree(source.data)
    root = tree.getroot()
    namespace, tag = qname(root)
    inventory: dict[str, Any] = {
        "root": root.tag,
        "schema_hints": [
            str(x) for x in cast(list[Any], tree.xpath('/processing-instruction("xml-model")'))
        ],
        "schema_location": root.get("{http://www.w3.org/2001/XMLSchema-instance}schemaLocation"),
        "elements": dict(
            sorted(Counter(str(x.tag) for x in root.iter() if isinstance(x.tag, str)).items())
        ),
    }
    if tag not in {"TEI", "teiCorpus"} or namespace not in {TEI, ""}:
        inventory["classification"] = (
            "schema" if tag in {"schema", "grammar", "schemaSpec"} else "non-tei-metadata"
        )
        return [], inventory
    if not namespace and not policy.allow_no_namespace:
        raise ConversionError("TEI namespace is absent; use --allow-no-namespace explicitly")
    inventory["classification"] = "tei"
    ids: set[str] = set()
    for node in root.iter():
        identity = node.get(f"{{{XML}}}id")
        if identity:
            if identity in ids:
                raise ConversionError(f"Duplicate xml:id: {identity}")
            ids.add(identity)
        ns, local = qname(node)
        if ns == XINCLUDE:
            raise ConversionError("XInclude requires explicit prior resolution")
        if ns == namespace and local in {"sourceDoc"}:
            raise ConversionError("sourceDoc transcription needs a dedicated reading-order adapter")
        if ns == namespace and local == "standOff" and len(node):
            raise ConversionError("standOff annotation projection is not implemented")
        if node.get("copyOf") or node.get("spanTo"):
            raise ConversionError(f"{local}: copyOf/spanTo requires explicit resolution")
    members = [x for x in root.iter() if qname(x) == (namespace, "TEI")]
    inventory["collection_metadata"] = [
        metadata(x, namespace) for x in root.iter() if qname(x) == (namespace, "teiCorpus")
    ]
    documents = []
    for member in members:
        texts = [x for x in member if qname(x) == (namespace, "text")]
        leaves: list[etree._Element] = []

        def descend(text: etree._Element, leaves: list[etree._Element]) -> None:
            groups = [x for x in text if qname(x) == (namespace, "group")]
            if groups:
                if (text.text or "").strip() or any((x.tail or "").strip() for x in text):
                    raise ConversionError("Text outside grouped document members")
                if any(isinstance(x.tag, str) and qname(x) != (namespace, "group") for x in text):
                    raise ConversionError("Non-group child requires explicit document splitting")
                if any(qname(x)[1] in {"body", "front", "back"} for x in text):
                    raise ConversionError(
                        "Mixed group and front/body/back requires explicit splitting"
                    )
                for group in groups:
                    if (group.text or "").strip():
                        raise ConversionError("Text outside grouped document members")
                    for child in group:
                        if qname(child) == (namespace, "text"):
                            descend(child, leaves)
                        elif isinstance(child.tag, str):
                            raise ConversionError("Non-text child of group requires an adapter")
                        if (child.tail or "").strip():
                            raise ConversionError("Tail text outside grouped document members")
            else:
                leaves.append(text)

        for text in texts:
            descend(text, leaves)
        for text in leaves:
            locator = tree.getpath(text)
            identity = hashlib.sha256((source.origin + "#" + locator).encode()).hexdigest()[:20]
            info = metadata(member, namespace)
            info["collection_headers"] = [
                metadata(a, namespace)
                for a in reversed(list(member.iterancestors()))
                if qname(a)[1] in {"TEI", "teiCorpus"}
            ]
            info["text_attributes"] = dict(text.attrib)
            if policy.facsimile == "zones":
                info["facsimile_zones"] = facsimile_zones(member, namespace)
            document = Document(identity, source.origin, locator, info)
            project(document, text, namespace, policy)
            documents.append(document)
    inventory["document_count"] = len(documents)
    if not documents:
        inventory["classification"] = "tei-metadata-only"
    return documents, inventory


def project(document: Document, text: etree._Element, namespace: str, policy: Policy) -> None:
    pieces: list[str] = []
    position = 0
    tree = text.getroottree()

    def emit(value: str | None) -> None:
        nonlocal position
        if value:
            pieces.append(value)
            position += len(value)
            if position > policy.max_slots:
                raise ConversionError("Document exceeds max_slots projection limit")

    def exclude(node: etree._Element, reason: str) -> None:
        document.excluded.append(
            {
                "path": tree.getpath(node),
                "reason": reason,
                "offset": position,
                "xml": fragment(node),
            }
        )

    def visit(node: etree._Element, parent: str | None) -> None:
        ns, tag = qname(node)
        if not tag:  # Comments/PIs have no reading text; raw source retains them.
            return
        path = tree.getpath(node)
        if ns == namespace and tag in {
            "subst",
            "del",
            "add",
            "restore",
            "transpose",
            "listTranspose",
            "join",
            "alt",
        }:
            raise ConversionError(
                f"{tag}: transcription/virtual-text policy is not implemented at {path}"
            )
        if ns == namespace:
            reason = None
            if tag in {"teiHeader", "titlePage", "docTitle", "docAuthor", "docImprint"}:
                reason = "document-metadata"
            elif tag in {"div", "list"} and node.get("type", "").lower() in TOC_TYPES:
                reason = "explicit-table-of-contents"
            elif tag == "note" and policy.notes == "separate":
                reason = "separate-note"
            if reason:
                exclude(node, reason)
                return
        record = Element(
            path,
            tag,
            ns,
            {str(k): str(v) for k, v in node.attrib.items()},
            parent,
            position,
            line=cast(int | None, node.sourceline),
        )
        document.elements.append(record)
        selected: list[etree._Element] | None = None
        if ns == namespace and tag in {"choice", "app"}:
            if (node.text or "").strip() or any((x.tail or "").strip() for x in node):
                raise ConversionError(f"Ambiguous text between {tag} alternatives at {path}")
            children = [x for x in node if isinstance(x.tag, str)]
            if tag == "choice":
                if policy.choice == "reject":
                    raise ConversionError(f"choice needs --choice original|edited at {path}")
                pairs = ({"orig", "reg"}, {"sic", "corr"}, {"abbr", "expan"})
                if any(qname(x)[0] != namespace for x in children):
                    raise ConversionError(f"Foreign choice alternative at {path}")
                tags = [qname(x)[1] for x in children]
                if len(tags) != 2 or not any(set(tags) == pair for pair in pairs):
                    raise ConversionError(f"Unsupported/ambiguous choice at {path}")
                wanted = (
                    {"orig", "sic", "abbr"}
                    if policy.choice == "original"
                    else {"reg", "corr", "expan"}
                )
                selected = [x for x in children if qname(x)[1] in wanted]
            else:
                if policy.apparatus == "reject":
                    raise ConversionError(f"app needs --apparatus lemma|witness at {path}")
                if (
                    node.get("from")
                    or node.get("to")
                    or any(
                        qname(x) != (namespace, "lem") and qname(x) != (namespace, "rdg")
                        for x in children
                    )
                ):
                    raise ConversionError(f"Unsupported stand-off/grouped apparatus at {path}")
                if policy.apparatus == "lemma":
                    selected = [x for x in children if qname(x)[1] == "lem"]
                else:
                    selected = [x for x in children if policy.witness in x.get("wit", "").split()]
            if len(selected) != 1:
                raise ConversionError(f"Expected exactly one selected {tag} reading at {path}")
            for child in children:
                if child not in selected:
                    exclude(child, "unselected-reading")
            visit(selected[0], path)
        else:
            emit(node.text)
            for child in node:
                visit(child, path)
                emit(child.tail)
        record.end = position
        if ns == namespace and (tag == "div" or re.fullmatch(r"div[1-7]", tag)):
            document.outline.append(
                {
                    "path": path,
                    "id": node.get(f"{{{XML}}}id"),
                    "type": node.get("type"),
                    "n": node.get("n"),
                    "heading_paths": [
                        tree.getpath(x) for x in node if qname(x) == (namespace, "head")
                    ],
                    "start": record.start,
                    "end": record.end,
                    "parent": parent,
                }
            )
        if record.start == record.end:
            document.diagnostics.append(
                {"code": "zero-width-element", "path": path, "offset": position, "tag": tag}
            )

    if (text.text or "").strip():
        raise ConversionError("Reading text outside front/body/back requires an explicit region")
    for region in text:
        ns, kind = qname(region)
        if not kind:
            continue
        if ns != namespace or kind not in {"front", "body", "back"}:
            raise ConversionError(f"Unsupported top-level text child: {region.tag}")
        start = position
        blocks = []
        # Preserve all character data inside regions, including whitespace and mixed-content tails.
        emit(region.text)
        if position > start:
            blocks.append((start, position, tree.getpath(region) + "/text()"))
        region_key = tree.getpath(region)
        region_record = Element(
            region_key,
            kind,
            ns,
            {str(k): str(v) for k, v in region.attrib.items()},
            None,
            start,
            line=cast(int | None, region.sourceline),
        )
        document.elements.append(region_record)
        for child in region:
            block_start = position
            visit(child, region_key)
            emit(child.tail)
            if position > block_start:
                blocks.append((block_start, position, tree.getpath(child)))
        region_record.end = position
        document.regions.append(Region(kind, start, position, blocks))
        if (region.tail or "").strip():
            raise ConversionError("Reading text between front/body/back regions is ambiguous")
    document.text = "".join(pieces)
    projected = {e.key: e for e in document.elements}
    for row in document.outline:
        row["headings"] = [
            document.text[projected[path].start : projected[path].end]
            for path in row.pop("heading_paths")
            if path in projected
        ]
    document.outline.sort(key=lambda row: (row["start"], -row["end"], row["path"]))
    if not document.text.strip():
        document.diagnostics.append({"code": "no-reading-text"})
