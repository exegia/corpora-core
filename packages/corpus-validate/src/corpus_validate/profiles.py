"""Legacy C-USX and CTEI archive profile checks without conversion machinery."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import re
import uuid
import zipfile
from functools import cache
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import yaml
from lxml import etree, isoschematron

CX = "urn:corpora:usx-extension:0.1"
CUSX_PROFILE = "corpora-cusx-package/0.1.0"
CUSX_STREAM = "cusx-itertext/v1"
CUSX_MEMBERS = {
    "document.usx",
    "document.json",
    "snapshot.json",
    "references.json",
    "mappings.json",
}
TEI_NS = "http://www.tei-c.org/ns/1.0"
XML_NS = "http://www.w3.org/XML/1998/namespace"
CTEI_NS = "urn:corpora:ctei:1"
CTEI_REQUIRED = {
    "manifest.yml",
    "toc.yml",
    "review.xml",
    "references.xml",
    "history.xml",
    "assets/mapping.xml",
    "presentations/styles.xml",
    "assets/conversion/receipt.json",
}
CTEI_ROLES = {
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "paragraph",
    "table",
    "note",
    "figure",
    "caption",
    "list",
    "poetry",
}
ET.register_namespace("cx", CX)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encoded(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _cusx_unit(parent: ET.Element, unit: dict[str, Any], depth: int = 0) -> None:
    if depth > 200:
        raise ValueError("C-USX source structure exceeds the supported nesting depth")
    node = ET.SubElement(parent, f"{{{CX}}}unit", {"type": unit["type"]})
    node.set("attributes", _encoded(unit.get("attrs", {})).decode())
    if unit.get("id") is not None:
        node.set("source-id", unit["id"])
    if unit.get("label") is not None:
        node.set("label", unit["label"])
    tokens = unit.get("tokens", [])
    children = unit.get("children", [])
    if tokens:
        para = ET.SubElement(node, "para", {"style": "p"})
        para.text = "".join(token["text"] + token.get("after", "") for token in tokens)
    for child in children:
        _cusx_unit(node, child, depth + 1)
    if tokens and not children:
        node.tail = "\n\n"


def _cusx_xml(document: dict[str, Any]) -> bytes:
    if not isinstance(document.get("metadata"), dict):
        raise ValueError("C-USX parsed document has no metadata")
    root = ET.Element("usx", {"version": "3.1", f"{{{CX}}}profile": CUSX_PROFILE})
    for unit in document["units"]:
        _cusx_unit(root, unit)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def validate_cusx(
    archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], name: str
) -> dict[str, Any]:
    """Check the C-USX profile and source projection without importing converters."""
    try:
        names = {info.filename for info in infos}
        if names != CUSX_MEMBERS | {"manifest.json"}:
            raise ValueError("unexpected or missing C-USX package members")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest["format"] != CUSX_PROFILE or set(manifest["files"]) != CUSX_MEMBERS:
            raise ValueError("unsupported C-USX package profile or file inventory")
        members = {member: archive.read(member) for member in CUSX_MEMBERS}
        if any(
            "sha256:" + _digest(data) != manifest["files"][member]
            for member, data in members.items()
        ):
            raise ValueError("C-USX member checksum mismatch")
        xml = members["document.usx"]
        if b"<!DOCTYPE" in xml.upper() or b"<!ENTITY" in xml.upper():
            raise ValueError("XML entity declarations are unsupported")
        root = ET.fromstring(xml)
        if root.tag != "usx" or root.get(f"{{{CX}}}profile") != CUSX_PROFILE:
            raise ValueError("invalid C-USX document profile")
        document = json.loads(members["document.json"])
        if _cusx_xml(document) != xml:
            raise ValueError("C-USX XML differs from the parsed document projection")
        snapshot = json.loads(members["snapshot.json"])
        if snapshot["endpoint"] != manifest["identity"] or snapshot["endpoint"][
            "revision"
        ] != "sha256:" + _digest(xml):
            raise ValueError("snapshot document identity or revision mismatch")
        if snapshot["stream_id"] != CUSX_STREAM or snapshot["text"] != "".join(root.itertext()):
            raise ValueError("snapshot text differs from the C-USX stream")
        if manifest["stream"] != {
            "id": CUSX_STREAM,
            "offset_unit": "unicode-scalar",
            "normalization": "preserve",
        }:
            raise ValueError("unsupported C-USX text stream conventions")
        if json.loads(members["references.json"]) != []:
            raise ValueError("conversion profile cannot claim approved references")
        mappings = json.loads(members["mappings.json"])
        if not isinstance(mappings, dict) or mappings.get("mappings") != []:
            raise ValueError("conversion profile cannot claim native mappings")
        stats = {
            "documents": 1,
            "characters": len(snapshot["text"]),
            "units": sum(node.tag == f"{{{CX}}}unit" for node in root.iter()),
        }
        return {
            "corpus": Path(name).stem,
            "path": name,
            "valid": True,
            "stats": stats,
            "reasons": [],
            "checks": {"cusx_package_integrity": True},
        }
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        RecursionError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        ET.ParseError,
    ) as error:
        return {
            "corpus": Path(name).stem,
            "path": name,
            "valid": False,
            "stats": {},
            "reasons": [str(error)],
            "checks": {"cusx_package_integrity": False},
        }


def _tei_xml(data: bytes) -> Any:
    if b"<!ENTITY" in data.upper() or re.search(rb"<!DOCTYPE[^>]*\[", data, re.I):
        raise ValueError("Internal DTD or entity-bearing XML is outside the CTEI profile")
    data = re.sub(rb"<!DOCTYPE[^>]*>", b"", data, flags=re.I)
    return etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))


@cache
def _tei_schemas() -> tuple[Any, Any, Any]:
    root = Path(__file__).parent / "profile"
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    return (
        etree.RelaxNG(
            etree.parse(
                io.BytesIO(gzip.decompress((root / "upstream/tei_all.rng.gz").read_bytes())), parser
            )
        ),
        etree.RelaxNG(etree.parse(str(root / "profile.rng"), parser)),
        isoschematron.Schematron(etree.parse(str(root / "profile.sch"), parser)),
    )


def _ctei_document(path: str) -> bool:
    parts = PurePosixPath(path).parts
    return len(parts) == 2 and parts[0].startswith("version_") and parts[1].endswith(".xml")


def _ctei_history(data: bytes) -> None:
    root = _tei_xml(data)
    if root.tag != f"{{{CTEI_NS}}}history" or not len(root):
        raise ValueError("CTEI history.xml has no version records")
    current = 0
    for row in root:
        if row.tag != f"{{{CTEI_NS}}}version" or row.get("current") not in {"true", "false"}:
            raise ValueError("Invalid CTEI history version")
        if not all(row.get(key) for key in ("id", "label", "title", "at")):
            raise ValueError("Incomplete CTEI history version")
        current += row.get("current") == "true"
    if current != 1:
        raise ValueError("CTEI history requires exactly one current version")


def validate_ctei(
    archive: zipfile.ZipFile, infos: list[zipfile.ZipInfo], name: str
) -> dict[str, Any]:
    """Check CTEI manifests, hashes, TEI schemas, sidecar pointers, and history."""
    checks: dict[str, bool] = {"archive": False}
    try:
        names = {info.filename for info in infos if not info.is_dir()}
        if not CTEI_REQUIRED <= names:
            raise ValueError("CTEI ZIP is incomplete")
        files = {member: archive.read(member) for member in names}
        manifest = yaml.safe_load(files["manifest.yml"])
        toc = yaml.safe_load(files["toc.yml"])
        if (
            uuid.UUID(manifest["uid"]).version != 4
            or manifest.get("format") != "corpus"
            or manifest.get("format_version") != "1"
            or manifest.get("tocFile") != "toc.yml"
        ):
            raise ValueError("Invalid CTEI manifest identity or format")
        if manifest["uid"] != toc["uid"] or manifest["version"] != toc["version"]:
            raise ValueError("CTEI manifest/TOC identity mismatch")
        assets = {
            member.removeprefix("assets/") for member in files if member.startswith("assets/")
        }
        inventory = [asset["path"] for asset in manifest["assets"]]
        if set(inventory) != assets or len(inventory) != len(assets):
            raise ValueError("CTEI manifest does not register every asset exactly once")
        receipt = json.loads(files["assets/conversion/receipt.json"])
        expected = {
            member: _digest(data)
            for member, data in files.items()
            if member != "assets/conversion/receipt.json"
        }
        if receipt["files"] != expected:
            raise ValueError("CTEI member hashes do not match conversion evidence")
        docs = toc.get("readingOrder", [])
        if not docs or len(docs) != len(set(docs)) or docs != [row["path"] for row in toc["files"]]:
            raise ValueError("Invalid CTEI reading order")
        if set(docs) != {member for member in files if _ctei_document(member)}:
            raise ValueError("CTEI TOC does not register all reading documents")
        roots = {
            member: _tei_xml(data)
            for member, data in files.items()
            if member.endswith(".xml") and not member.startswith("assets/source")
        }
        ids = {
            (member, node.get(f"{{{XML_NS}}}id"))
            for member, root in roots.items()
            for node in root.iter()
            if node.get(f"{{{XML_NS}}}id")
        }

        def local_target(target: str) -> None:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or (parsed.path, parsed.fragment) not in ids:
                raise ValueError("CTEI sidecar has a missing or non-local target")

        upstream, profile, schematron = _tei_schemas()
        for document in docs:
            root = roots[document]
            if any(not schema.validate(root) for schema in (upstream, profile, schematron)):
                raise ValueError("CTEI reading document fails TEI schema: " + document)
            for ref in root.xpath("//t:ref[@type='resolved']", namespaces={"t": TEI_NS}):
                parsed = urlsplit(ref.get("target"))
                local_target(
                    str(
                        PurePosixPath(document).parent
                        / (parsed.path or PurePosixPath(document).name)
                    )
                    + "#"
                    + parsed.fragment
                )
            for graphic in root.xpath("//t:graphic", namespaces={"t": TEI_NS}):
                asset = graphic.get("url", "").removeprefix("../")
                if asset not in files or not asset.startswith("assets/"):
                    raise ValueError("CTEI graphic has no registered asset")
        if not upstream.validate(roots["review.xml"]):
            raise ValueError("CTEI review.xml fails TEI P5 schema")
        for annotation in roots["review.xml"].xpath("//t:annotation", namespaces={"t": TEI_NS}):
            for target in annotation.get("target", "").split():
                local_target(target)
        for reference in roots["references.xml"]:
            local_target(reference.get("source", ""))
            if reference.get("status") == "resolved":
                local_target(reference.get("target", ""))
        for asset in roots["assets/mapping.xml"]:
            if asset.get("path") not in files:
                raise ValueError("CTEI mapping names a missing asset")
            if asset.get("target"):
                local_target(asset.get("target"))
        for style in roots["presentations/styles.xml"]:
            if style.tag != f"{{{CTEI_NS}}}style" or set(style.attrib) != {"semantic", "targets"}:
                raise ValueError("CTEI presentations must contain semantic roles only")
            if style.get("semantic") not in CTEI_ROLES:
                raise ValueError("CTEI presentations contain an unsupported semantic role")
            for target in style.get("targets", "").split():
                local_target(target)
        _ctei_history(files["history.xml"])
        checks = {
            key: True
            for key in (
                "archive",
                "metadata",
                "assets",
                "hashes",
                "tei-p5",
                "profile",
                "references",
                "review",
                "history",
            )
        }
        stats = {
            "documents": len(docs),
            "assets": len(assets),
            "review_items": len(
                roots["review.xml"].xpath("//t:annotation", namespaces={"t": TEI_NS})
            ),
        }
        return {
            "corpus": manifest["name"],
            "path": name,
            "valid": True,
            "stats": stats,
            "reasons": [],
            "checks": checks,
            "source_verified": False,
        }
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        AttributeError,
        IndexError,
        RecursionError,
        RuntimeError,
        NotImplementedError,
        zipfile.BadZipFile,
        etree.XMLSyntaxError,
        yaml.YAMLError,
    ) as error:
        return {
            "corpus": Path(name).stem,
            "path": name,
            "valid": False,
            "stats": None,
            "reasons": [str(error)],
            "checks": checks,
        }
