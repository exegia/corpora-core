"""Deterministic TEI projection and official Text-Fabric serialization."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from lxml import etree
from tf.fabric import Fabric

from .acquire import Limits, acquire
from .model import ConversionError, Document, Element, Policy, Source
from .parse import TEI, ZONE_COORDINATES, parse, secure_tree

ZONE_FEATURES = tuple("facs_" + key for key in ZONE_COORDINATES)


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def zone_features(
    doc: Document, element: Element, unresolved: list[dict[str, Any]]
) -> dict[str, Any]:
    """Resolve one local `@facs` pointer to its surface label and integer zone coordinates."""
    raw = element.attributes.get("facs")
    if raw is None:
        return {}
    zones = doc.metadata.get("facsimile_zones", {})
    tokens = raw.split()
    if len(tokens) != 1 or not tokens[0].startswith("#") or tokens[0][1:] not in zones:
        unresolved.append(
            {
                "document": doc.id,
                "path": element.key,
                "attribute": "facs",
                "reference": raw,
                "reason": "facs must name exactly one local facsimile surface or zone",
            }
        )
        return {}
    zone = zones[tokens[0][1:]]
    features: dict[str, Any] = {"facs_surface": zone["surface"]}
    for key in ZONE_COORDINATES:
        value = zone[key]
        if not re.fullmatch(r"-?[0-9]+", value):
            raise ConversionError(
                f"{tokens[0]}: {key}={value!r} is not an integer; "
                "zone features need integer coordinates in a declared unit"
            )
        features["facs_" + key] = int(value)
    return features


def page_spans(doc: Document) -> tuple[list[tuple[Element, int, int]], int]:
    """Pages run from each TEI `pb` to the next `pb` or the end of its region.

    Returns (pb, start, end) spans and the count of region characters before any `pb`.
    """
    breaks = [e for e in doc.elements if e.namespace == TEI and e.tag == "pb"]
    spans = []
    for index, pb in enumerate(breaks):
        region = next((r for r in doc.regions if r.start <= pb.start <= r.end), None)
        end = region.end if region else len(doc.text)
        if index + 1 < len(breaks):
            end = min(end, breaks[index + 1].start)
        spans.append((pb, pb.start, end))
    covered = sum(end - start for _, start, end in spans)
    total = sum(r.end - r.start for r in doc.regions)
    return spans, total - covered


def export(documents: list[Document], destination: Path, policy: Policy) -> dict[str, Any]:
    """Character slots preserve Unicode scalar offsets without guessing tokenization."""
    total_slots = sum(len(doc.text) for doc in documents if doc.text.strip())
    memberships = sum(
        len(doc.text)
        + sum(r.end - r.start for r in doc.regions)
        + sum(end - start for r in doc.regions for start, end, _ in r.blocks)
        + sum(e.end - e.start for e in doc.elements)
        for doc in documents
        if doc.text.strip()
    )
    if total_slots > policy.max_slots or memberships > policy.max_memberships:
        raise ConversionError("Projected graph exceeds slot/membership limits")
    node: dict[str, dict[int, Any]] = defaultdict(dict)
    edge: dict[str, dict[int, set[int]]] = defaultdict(dict)
    specs: dict[str, list[tuple[str, list[int], dict[str, Any]]]] = defaultdict(list)
    lookup: dict[str, int] = {}
    relationships: list[tuple[str, str]] = []
    offsets: dict[str, int] = {}
    attribute_features: dict[str, str] = {}
    unresolved: list[dict[str, Any]] = []
    pages: dict[str, Any] = {"count": 0, "empty": [], "characters_outside_pages": 0}
    slot = 0
    for doc in documents:
        if not doc.text.strip():
            continue
        offsets[doc.id] = slot
        for char in doc.text:
            slot += 1
            node["otype"][slot] = "character"
            node["text"][slot] = char
        if not doc.text:
            continue
        base = offsets[doc.id]
        specs["document"].append(
            (doc.id, list(range(base + 1, slot + 1)), {"document": doc.id, "source": doc.source})
        )
        for index, region in enumerate(doc.regions, 1):
            if region.start == region.end:
                continue
            key = f"{doc.id}:region:{index}"
            specs["region"].append(
                (
                    key,
                    list(range(base + region.start + 1, base + region.end + 1)),
                    {"region": f"{index}:{region.kind}"},
                )
            )
            for number, (start, end, path) in enumerate(region.blocks, 1):
                specs["block"].append(
                    (
                        f"{key}:block:{number}",
                        list(range(base + start + 1, base + end + 1)),
                        {"block": number, "source_path": path},
                    )
                )
        for element in doc.elements:
            if element.start == element.end:
                continue
            key = doc.id + ":" + element.key
            features: dict[str, Any] = {
                "tei_tag": element.tag,
                "tei_namespace": element.namespace,
                "attributes": json.dumps(element.attributes, ensure_ascii=False, sort_keys=True),
                "source_path": element.key,
                "start": element.start,
                "end": element.end,
            }
            for attr, value in element.attributes.items():
                local = etree.QName(attr).localname
                safe = re.sub(r"[^a-zA-Z0-9_]", "_", local)
                name = "attr_" + safe + "_" + hashlib.sha256(attr.encode()).hexdigest()[:12]
                attribute_features[attr] = name
                features[name] = value
            if policy.facsimile == "zones":
                features.update(zone_features(doc, element, unresolved))
            specs["element"].append(
                (key, list(range(base + element.start + 1, base + element.end + 1)), features)
            )
            if element.parent:
                relationships.append((key, doc.id + ":" + element.parent))
        if policy.milestones == "pages":
            spans, outside = page_spans(doc)
            pages["characters_outside_pages"] += outside
            for pb, start, end in spans:
                label = pb.attributes.get("n", "")
                if start == end:
                    pages["empty"].append({"document": doc.id, "path": pb.key, "n": label})
                    continue
                features = {"page": label, "source_path": pb.key, "start": start, "end": end}
                if policy.facsimile == "zones":
                    features.update(zone_features(doc, pb, unresolved))
                specs["page"].append(
                    (
                        doc.id + ":page:" + pb.key,
                        list(range(base + start + 1, base + end + 1)),
                        features,
                    )
                )
                pages["count"] += 1
    if not slot:
        raise ConversionError("No reading text; metadata-only inputs cannot create a TF corpus")
    for kind in ("document", "region", "block", "element", "page"):
        for key, slots, features in specs[kind]:
            number = len(node["otype"]) + 1
            lookup[key] = number
            node["otype"][number] = kind
            edge["oslots"][number] = set(slots)
            for name, value in features.items():
                node[name][number] = value
    for child, parent in relationships:
        if child in lookup and parent in lookup:
            edge["parent"][lookup[child]] = {lookup[parent]}
    for doc in documents:
        ids = {
            e.attributes["{http://www.w3.org/XML/1998/namespace}id"]: doc.id + ":" + e.key
            for e in doc.elements
            if "{http://www.w3.org/XML/1998/namespace}id" in e.attributes
        }
        for element in doc.elements:
            source = lookup.get(doc.id + ":" + element.key)
            for attr in ("ref", "target", "corresp", "ana", "next", "prev", "sameAs"):
                for reference in element.attributes.get(attr, "").split():
                    target = (
                        lookup.get(ids.get(reference[1:], ""))
                        if reference.startswith("#")
                        else None
                    )
                    if source and target:
                        edge.setdefault("link_" + attr, {}).setdefault(source, set()).add(target)
                    else:
                        unresolved.append(
                            {
                                "document": doc.id,
                                "path": element.key,
                                "attribute": attr,
                                "reference": reference,
                                "reason": "external, excluded, zero-width or unresolved",
                            }
                        )
    ints = {"start", "end", "block", *ZONE_FEATURES}
    meta: dict[str, Any] = {name: {"valueType": "int" if name in ints else "str"} for name in node}
    meta.update({name: {"valueType": "str"} for name in edge})
    meta[""] = {"converter": "corpora-tei-to-tf", "slotPolicy": "Unicode scalar; no normalization"}
    meta["otext"] = {
        "fmt:text-orig-full": "{text}",
        "sectionTypes": "document,region,block",
        "sectionFeatures": "document,region,block",
    }
    destination.mkdir()
    writer = Fabric(locations=str(destination), silent="deep")
    if not writer.save(
        nodeFeatures=dict(node), edgeFeatures=dict(edge), metaData=meta, silent="deep"
    ):
        raise ConversionError("Text-Fabric writer rejected the projected graph")
    # Normalize only the known writer output: timestamps are operational metadata,
    # and explicit unvalued edge sources interoperate with static validators.
    for feature_path in destination.glob("*.tf"):
        header, data = feature_path.read_text(encoding="utf-8").split("\n\n", 1)
        header = "\n".join(
            line for line in header.splitlines() if not line.startswith("@dateWritten=")
        )
        if feature_path.stem in edge:
            rows = []
            implicit = 1
            for line in data.splitlines():
                if "\t" in line:
                    current, targets = line.split("\t", 1)
                    implicit = int(current)
                else:
                    targets = line
                rows.append(f"{implicit}\t{targets}")
                implicit += 1
            data = "\n".join(rows) + "\n"
        feature_path.write_text(header + "\n\n" + data, encoding="utf-8")
    return {
        "max_slot": slot,
        "max_node": len(node["otype"]),
        "node_ids": lookup,
        "attribute_features": attribute_features,
        "unresolved_references": unresolved,
        "document_slot_offsets": offsets,
        **({"pages": pages} if policy.milestones == "pages" else {}),
    }


def validate_schema(source: Source, schema: Path) -> None:
    """Validate with a caller-supplied self-contained RNG/XSD; never auto-fetch schemas."""
    schema_tree = secure_tree(schema.read_bytes())
    for node in schema_tree.iter():
        if not isinstance(node.tag, str):
            continue
        if etree.QName(node).localname in {"include", "import", "externalRef", "redefine"}:
            raise ConversionError("Schema must be self-contained (no include/import/externalRef)")
    root = etree.QName(schema_tree.getroot())
    if root.namespace == "http://relaxng.org/ns/structure/1.0":
        validator = etree.RelaxNG(schema_tree)
    elif root.namespace == "http://www.w3.org/2001/XMLSchema":
        validator = etree.XMLSchema(schema_tree)
    else:
        raise ConversionError("Expected a RELAX NG XML or XSD schema")
    if not validator.validate(secure_tree(source.data)):
        raise ConversionError(f"Schema validation failed: {validator.error_log.last_error}")


def convert(
    inputs: list[str],
    output: Path,
    policy: Policy | None = None,
    limits: Limits | None = None,
    revision: str | None = None,
    schema: Path | None = None,
    sources: list[Source] | None = None,
) -> dict[str, Any]:
    """Create a new output bundle; original sources and existing outputs are never overwritten."""
    policy = policy or Policy()
    limits = limits or Limits()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ConversionError(f"Output already exists: {output}")
    # Acquisition and interpretation complete before allocating any output.
    acquired = sources if sources is not None else acquire(inputs, limits, revision)
    documents: list[Document] = []
    inventory = []
    for source in acquired:
        digest = hashlib.sha256(source.data).hexdigest()
        entry: dict[str, Any] = {
            "name": source.name,
            "origin": source.origin,
            "revision": source.revision,
            "sha256": digest,
            "bytes": len(source.data),
            "source_file": f"sources/{digest}",
        }
        suffix = Path(source.name).suffix.lower()
        if suffix in {".xml", ".tei", ".odd", ".rng", ".xsd"} or (
            not suffix and source.data.lstrip().startswith(b"<")
        ):
            try:
                parsed, details = parse(source, policy)
                if details["classification"] == "tei" and schema:
                    validate_schema(source, schema)
                entry.update(details)
                documents.extend(parsed)
            except ConversionError as exc:
                raise ConversionError(f"{source.origin}: {exc}") from exc
        else:
            entry["classification"] = "repository-metadata"
        inventory.append(entry)
    if not any(doc.text.strip() for doc in documents):
        raise ConversionError("No TEI reading content found; headers/manifests are not corpus text")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive reservation prevents concurrent conversions from claiming the same destination.
    output.mkdir()
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (stage / "sources").mkdir()
        for source in acquired:
            digest = hashlib.sha256(source.data).hexdigest()
            (stage / "sources" / digest).write_bytes(source.data)
        (stage / "documents").mkdir()
        for doc in documents:
            write_json(stage / "documents" / f"{doc.id}.json", asdict(doc))
            (stage / "documents" / f"{doc.id}.txt").write_text(doc.text, encoding="utf-8")
        graph = export(documents, stage / "tf", policy)
        # Save emits no semantic proof: independently check emitted bytes via real loader below.
        reader = Fabric(locations=str(stage / "tf"), silent="deep")
        api = reader.load("text document region block tei_tag", silent="deep")
        if api is False:
            raise ConversionError("Export failed real Text-Fabric loader acceptance")
        for doc in documents:
            number = graph["node_ids"].get(doc.id)
            if number is not None and api.T.text(number) != doc.text:
                raise ConversionError(f"Text round-trip failed for {doc.id}")
            if policy.milestones == "pages":
                for pb, start, end in page_spans(doc)[0]:
                    number = graph["node_ids"].get(doc.id + ":page:" + pb.key)
                    if number is not None and api.T.text(number) != doc.text[start:end]:
                        raise ConversionError(f"Page round-trip failed at {pb.key}")
        # Do not distribute runtime-specific cache files.
        for path in (stage / "tf").iterdir():
            if path.is_dir():
                shutil.rmtree(path)
        manifest = {
            "format": "corpora-tei-to-tf/1",
            "policy": asdict(policy),
            "sources": inventory,
            "documents": [doc.id for doc in documents],
            "metadata_only_documents": [doc.id for doc in documents if not doc.text.strip()],
            "schema_validation": str(schema) if schema else "not requested",
            "graph": graph,
            "verification": {"tf_load": "passed", "exact_text": "passed"},
            "limitations": [
                "Character slots are not linguistic tokens",
                "Zero-width elements retain offsets in document JSON",
                "Reference strings without projected targets remain in manifest",
                "Section levels are document/region/top-level block; see outline",
            ],
        }
        write_json(stage / "manifest.json", manifest)
        hashes = {
            str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(stage.rglob("*"))
            if path.is_file()
        }
        write_json(stage / "checksums.json", hashes)
        os.replace(stage, output)  # Replaces only this process's empty reservation.
        return manifest
    except BaseException:
        shutil.rmtree(stage)
        output.rmdir()  # Only remove our empty reservation, never another directory's contents.
        raise
