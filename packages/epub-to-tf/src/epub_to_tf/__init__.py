"""Export validated EPUB reading projections as deterministic Text-Fabric bundles."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from typing import Any
from zipfile import ZipFile

from tf.fabric import Fabric

from .reading import annotate_scope
from .repair import RepairRejected, repair_archive
from .semantics import annotate_document, extract_toc, toc_by_member


class ConversionError(ValueError):
    """Input or projected graph cannot be exported faithfully."""


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _write_graph(
    documents: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    references: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    reading_slots: dict[str, list[str]],
    destination: Path,
) -> dict[str, Any]:
    node: dict[str, dict[int, Any]] = defaultdict(dict)
    edge: dict[str, dict[int, set[int]]] = defaultdict(dict)
    specs: list[tuple[str, str, list[int], dict[str, Any], str | None]] = []
    lookup: dict[str, int] = {}
    slot = 0
    for document in documents:
        start = slot
        doc_key = "document:" + document["id"]
        for char, display in zip(document["text"], reading_slots[doc_key], strict=True):
            slot += 1
            node["otype"][slot] = "character"
            node["text"][slot] = char
            if display:
                node["reading"][slot] = display
        if slot == start:
            raise ConversionError(f"Empty reading spine item: {document['member']}")
        document_assets = [
            asset
            for asset in assets
            if asset["scope"] == "document" and asset["scope_id"] == document["id"]
        ]
        document_images = [asset for asset in document_assets if asset["kind"] == "image"]
        specs.append(
            (
                "document",
                doc_key,
                list(range(start + 1, slot + 1)),
                {
                    "document": document["id"],
                    "source_member": document["member"],
                    "image_assets": json.dumps(document_images, ensure_ascii=False, sort_keys=True),
                    "asset_refs": json.dumps(document_assets, ensure_ascii=False, sort_keys=True),
                    "toc_entries": json.dumps(
                        document["toc_entries"], ensure_ascii=False, sort_keys=True
                    ),
                    "reading_length": len(document["reading_text"]),
                },
                None,
            )
        )
        for element in document["elements"]:
            if element["end"] == element["start"]:
                continue
            key = doc_key + ":" + element["key"]
            parent = doc_key + ":" + element["parent"] if element["parent"] else doc_key
            specs.append(
                (
                    "element",
                    key,
                    list(range(start + element["start"] + 1, start + element["end"] + 1)),
                    {
                        "xhtml_tag": element["tag"],
                        "attributes": json.dumps(
                            element["attributes"], ensure_ascii=False, sort_keys=True
                        ),
                        "source_member": document["member"],
                        "source_byte": element["source_byte"],
                        "start": element["start"],
                        "end": element["end"],
                        "reading_start": element["reading_start"],
                        "reading_end": element["reading_end"],
                        **{
                            name: element[name]
                            for name in (
                                "semantic_kind",
                                "semantic_label",
                                "heading_level",
                                "verse_number",
                                "link_kind",
                                "link_href",
                                "link_target_member",
                                "link_fragment",
                                "link_external",
                            )
                            if name in element and element[name] != ""
                        },
                    },
                    parent,
                )
            )
    for note in notes:
        start = slot
        note_key = "note:" + note["source_key"]
        for char, display in zip(note["text"], reading_slots[note_key], strict=True):
            slot += 1
            node["otype"][slot] = "character"
            node["text"][slot] = char
            if display:
                node["reading"][slot] = display
        specs.append(
            (
                "note",
                note_key,
                list(range(start + 1, slot + 1)),
                {
                    "source_key": note["source_key"],
                    "source_member": note["member"],
                    "note_fragment": note["fragment"],
                    "note_kind": note["kind"],
                    "asset_refs": json.dumps(
                        [
                            asset
                            for asset in assets
                            if asset["scope"] == "note" and asset["scope_id"] == note["source_key"]
                        ],
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                },
                None,
            )
        )
        for element in note["elements"]:
            if element["end"] == element["start"]:
                continue
            parent = note_key + ":" + element["parent"] if element["parent"] else note_key
            specs.append(
                (
                    "element",
                    note_key + ":" + element["key"],
                    list(range(start + element["start"] + 1, start + element["end"] + 1)),
                    {
                        "xhtml_tag": element["tag"],
                        "attributes": json.dumps(
                            element["attributes"], ensure_ascii=False, sort_keys=True
                        ),
                        "source_member": note["member"],
                        "source_byte": element["source_byte"],
                        "start": element["start"],
                        "end": element["end"],
                        "reading_start": element["reading_start"],
                        "reading_end": element["reading_end"],
                    },
                    parent,
                )
            )
    # TF requires one contiguous node block per type.
    for kind in ("document", "note", "element"):
        for spec_kind, key, slots, features, _ in specs:
            if spec_kind != kind:
                continue
            number = len(node["otype"]) + 1
            lookup[key] = number
            node["otype"][number] = kind
            edge["oslots"][number] = set(slots)
            for name, value in features.items():
                node[name][number] = value
    for _, key, _, _, parent in specs:
        if parent and key in lookup and parent in lookup:
            edge["parent"][lookup[key]] = {lookup[parent]}
    for reference in references:
        anchor_key = "document:" + reference["document_id"] + ":" + reference["anchor_key"]
        note_key = "note:" + reference["target_key"]
        anchor = lookup.get(anchor_key)
        target = lookup.get(note_key)
        if anchor is None or target is None:
            raise ConversionError(f"Missing projected note link: {reference['href']}")
        edge["noteref"].setdefault(anchor, set()).add(target)
        node["note_href"][anchor] = reference["href"]
        node["note_label"][anchor] = reference["label"]
        node["note_target_key"][anchor] = reference["target_key"]
        node["note_anchor_key"][anchor] = f"{reference['member']}@{reference['source_byte']}"
    reading_empty = not node["reading"]
    if reading_empty:
        # TF needs the declared default-format feature even for a blank book.
        node["reading"][1] = ""
    meta: dict[str, dict[str, str]] = {
        name: {
            "valueType": "int"
            if name
            in {
                "start",
                "end",
                "source_byte",
                "reading_start",
                "reading_end",
                "reading_length",
                "heading_level",
                "link_external",
            }
            else "str"
        }
        for name in node
    }
    meta.update({name: {"valueType": "str"} for name in edge})
    meta[""] = {
        "converter": "corpora-epub-to-tf",
        "slotPolicy": "one Unicode scalar per original source character",
        "readingPolicy": "collapse layout whitespace runs; preserve preformatted spans",
    }
    meta["otext"] = {
        "fmt:text-orig-full": "{reading}",
        "fmt:text-source-full": "{text}",
        "sectionTypes": "document",
        "sectionFeatures": "document",
    }
    destination.mkdir(exist_ok=True)
    if not Fabric(locations=str(destination), silent="deep").save(
        nodeFeatures=dict(node), edgeFeatures=dict(edge), metaData=meta, silent="deep"
    ):
        raise ConversionError("Text-Fabric writer rejected projected graph")
    for path in destination.glob("*.tf"):
        header, data = path.read_text(encoding="utf-8").split("\n\n", 1)
        header = "\n".join(
            line for line in header.splitlines() if not line.startswith("@dateWritten=")
        )
        if path.stem == "reading" and reading_empty:
            data = "1\t\n"
        if path.stem in edge:
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
        path.write_text(header + "\n\n" + data, encoding="utf-8")
    return {"max_slot": slot, "max_node": len(node["otype"]), "node_ids": lookup}


def _check(source: Path, checker: Path, max_slots: int | None) -> tuple[int, dict[str, Any]]:
    command = [str(checker), str(source)]
    if max_slots is not None:
        command.extend(["--max-slots", str(max_slots)])
    checked = subprocess.run(command, capture_output=True, text=True, check=False)
    if checked.returncode not in {0, 1}:
        raise ConversionError(checked.stderr.strip() or "EPUB checker failed")
    report: dict[str, Any] = json.loads(checked.stdout)
    return checked.returncode, report


def convert(
    source: Path,
    output: Path,
    checker: Path,
    *,
    repair: bool = False,
    max_slots: int | None = None,
) -> dict[str, Any]:
    """Validate and export one local EPUB; existing destinations are never overwritten."""
    source = source.absolute()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ConversionError(f"Output already exists: {output}")
    original = source.read_bytes()
    if max_slots is not None and not 1 <= max_slots <= 8_000_000:
        raise ConversionError("--max-slots must be between 1 and 8000000")
    status, report = _check(source, checker, max_slots)
    if report["archive_sha256"] != hashlib.sha256(original).hexdigest():
        raise ConversionError("EPUB changed between validation and export")
    initial_findings = report["findings"]
    candidate_bytes = original
    repair_ledger: list[dict[str, Any]] = []
    if status and repair:
        try:
            candidate_bytes, repair_ledger = repair_archive(original, report)
        except RepairRejected as error:
            raise ConversionError(f"EPUB repair blocked: {error}") from error
        with tempfile.TemporaryDirectory(prefix="epub-repair-") as temp:
            candidate_path = Path(temp) / "candidate.epub"
            candidate_path.write_bytes(candidate_bytes)
            status, report = _check(candidate_path, checker, max_slots)
            if report["archive_sha256"] != hashlib.sha256(candidate_bytes).hexdigest():
                raise ConversionError("Repaired EPUB changed during final validation")
    if status or not report["documents"]:
        findings = [
            f"{item['member']}: {diagnostic['code']}: {diagnostic['message']}"
            for item in report["findings"]
            for diagnostic in item["report"]["diagnostics"]
            if diagnostic["blocking"]
        ]
        raise ConversionError("EPUB validation blocked export: " + "; ".join(findings))
    reading_slots: dict[str, list[str]] = {}
    links: list[dict[str, Any]] = []
    with ZipFile(BytesIO(candidate_bytes)) as archive:
        members = set(archive.namelist())
        try:
            toc = extract_toc(archive, report["navigation"])
        except ValueError as error:
            raise ConversionError(str(error)) from error
    member_toc = toc_by_member(toc)
    for document in report["documents"]:
        document_assets = [
            asset
            for asset in report["assets"]
            if asset["scope"] == "document" and asset["scope_id"] == document["id"]
        ]
        reading_slots["document:" + document["id"]] = annotate_scope(document, document_assets)
        document["toc_entries"] = member_toc.get(document["member"], [])
        links.extend(annotate_document(document, members))
    for note in report["notes"]:
        note_assets = [
            asset
            for asset in report["assets"]
            if asset["scope"] == "note" and asset["scope_id"] == note["source_key"]
        ]
        reading_slots["note:" + note["source_key"]] = annotate_scope(note, note_assets)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (stage / "sources").mkdir()
        (stage / "sources" / "original.epub").write_bytes(original)
        if repair_ledger:
            (stage / "sources" / "repaired.epub").write_bytes(candidate_bytes)
            _json(stage / "sources" / "repair-ledger.json", repair_ledger)
            _json(
                stage / "sources" / "validation.json",
                {"initial_findings": initial_findings, "final_findings": report["findings"]},
            )
        (stage / "documents").mkdir()
        for index, document in enumerate(report["documents"], 1):
            _json(stage / "documents" / f"{index:04}.json", document)
            (stage / "documents" / f"{index:04}.txt").write_text(document["text"], encoding="utf-8")
            (stage / "documents" / f"{index:04}.reading.txt").write_text(
                document["reading_text"], encoding="utf-8"
            )
        (stage / "notes").mkdir()
        for index, note in enumerate(report["notes"], 1):
            _json(stage / "notes" / f"{index:04}.json", note)
            (stage / "notes" / f"{index:04}.txt").write_text(note["text"], encoding="utf-8")
            (stage / "notes" / f"{index:04}.reading.txt").write_text(
                note["reading_text"], encoding="utf-8"
            )
        (stage / "tf" / "assets").mkdir(parents=True)
        with ZipFile(BytesIO(candidate_bytes)) as archive:
            for asset in report["assets"]:
                data = archive.read(asset["target_member"])
                if asset["source_end"] is not None:
                    data = data[asset["source_byte"] : asset["source_end"]]
                if (
                    len(data) != asset["bytes"]
                    or hashlib.sha256(data).hexdigest() != asset["sha256"]
                ):
                    raise ConversionError(
                        f"Asset changed after validation: {asset['target_member']}"
                    )
                suffix = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/gif": ".gif",
                    "image/webp": ".webp",
                    "image/svg+xml": ".svg",
                    "image/avif": ".avif",
                    "audio/mpeg": ".mp3",
                    "audio/mp4": ".m4a",
                    "audio/ogg": ".ogg",
                    "audio/webm": ".webm",
                    "video/mp4": ".mp4",
                    "video/webm": ".webm",
                    "video/ogg": ".ogv",
                    "text/vtt": ".vtt",
                    "application/ttml+xml": ".ttml",
                    "application/pdf": ".pdf",
                    "application/mathml+xml": ".mml",
                }.get(asset["media_type"], ".bin")
                asset["tf_path"] = "assets/" + asset["sha256"] + suffix
                asset["file"] = "tf/" + asset["tf_path"]
                (stage / asset["file"]).write_bytes(data)
        report["images"] = [asset for asset in report["assets"] if asset["kind"] == "image"]
        graph = _write_graph(
            report["documents"],
            report["notes"],
            report["note_references"],
            report["assets"],
            reading_slots,
            stage / "tf",
        )
        features = (
            "text reading document source_member xhtml_tag image_assets asset_refs toc_entries"
        )
        if report["notes"]:
            features += " note_kind source_key noteref"
        api = Fabric(locations=str(stage / "tf"), silent="deep").load(features, silent="deep")
        if api is False:
            raise ConversionError("Real Text-Fabric loader rejected export")
        for document in report["documents"]:
            node = graph["node_ids"]["document:" + document["id"]]
            if api.T.text(node) != document["reading_text"]:
                raise ConversionError(f"Reading text round-trip failed: {document['member']}")
            if api.T.text(node, fmt="text-source-full") != document["text"]:
                raise ConversionError(f"Source text round-trip failed: {document['member']}")
            if json.loads(api.F.toc_entries.v(node)) != document["toc_entries"]:
                raise ConversionError(f"TOC round-trip failed: {document['member']}")
            image_assets = [
                image
                for image in report["images"]
                if image["scope"] == "document" and image["scope_id"] == document["id"]
            ]
            if json.loads(api.F.image_assets.v(node)) != image_assets:
                raise ConversionError(f"Image round-trip failed: {document['member']}")
            asset_refs = [
                asset
                for asset in report["assets"]
                if asset["scope"] == "document" and asset["scope_id"] == document["id"]
            ]
            if json.loads(api.F.asset_refs.v(node)) != asset_refs:
                raise ConversionError(f"Asset round-trip failed: {document['member']}")
        for note in report["notes"]:
            number = graph["node_ids"]["note:" + note["source_key"]]
            if api.T.text(number) != note["reading_text"]:
                raise ConversionError(f"Note reading text round-trip failed: {note['source_key']}")
            if api.T.text(number, fmt="text-source-full") != note["text"]:
                raise ConversionError(f"Note source text round-trip failed: {note['source_key']}")
            note_assets = [
                asset
                for asset in report["assets"]
                if asset["scope"] == "note" and asset["scope_id"] == note["source_key"]
            ]
            if json.loads(api.F.asset_refs.v(number)) != note_assets:
                raise ConversionError(f"Note asset round-trip failed: {note['source_key']}")
        for reference in report["note_references"]:
            anchor = graph["node_ids"][
                "document:" + reference["document_id"] + ":" + reference["anchor_key"]
            ]
            target = graph["node_ids"]["note:" + reference["target_key"]]
            if target not in api.E.noteref.f(anchor):
                raise ConversionError(f"Note link round-trip failed: {reference['href']}")
        for path in (stage / "tf").iterdir():
            if path.is_dir() and path.name in {".tf", ".cfm"}:
                shutil.rmtree(path)
        manifest = {
            "format": "corpora-epub-to-tf/2",
            "source": {
                "sha256": hashlib.sha256(original).hexdigest(),
                "file": "sources/original.epub",
            },
            "validated_source": {
                "sha256": report["archive_sha256"],
                "file": "sources/repaired.epub" if repair_ledger else "sources/original.epub",
            },
            "repair_ledger": repair_ledger,
            "max_slots": max_slots or 1_000_000,
            "members": report["members"],
            "identifier": report["identifier"],
            "metadata": report["metadata"],
            "navigation": report["navigation"],
            "toc": toc,
            "links": links,
            "reading_policy": (
                "layout whitespace runs to one space or newline; preformatted text exact"
            ),
            "documents": [doc["id"] for doc in report["documents"]],
            "notes": [note["source_key"] for note in report["notes"]],
            "note_references": report["note_references"],
            "images": report["images"],
            "assets": report["assets"],
            "graph": graph,
        }
        _json(stage / "manifest.json", manifest)
        _json(
            stage / "checksums.json",
            {
                str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(stage.rglob("*"))
                if path.is_file()
            },
        )
        os.replace(stage, output)
        return manifest
    except BaseException:
        shutil.rmtree(stage)
        output.rmdir()
        raise


def main() -> None:
    """Run the local converter from a shell."""
    parser = argparse.ArgumentParser(description="Convert a local reflowable EPUB to Text-Fabric")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--checker", type=Path, default=Path("target/debug/corpora-epub-check"))
    parser.add_argument(
        "--repair", action="store_true", help="Audit and repair bounded XHTML syntax"
    )
    parser.add_argument(
        "--max-slots", type=int, help="Explicit character-slot limit (up to 8000000)"
    )
    args = parser.parse_args()
    try:
        manifest = convert(
            args.source, args.output, args.checker, repair=args.repair, max_slots=args.max_slots
        )
    except ConversionError as error:
        parser.error(str(error))
    print(json.dumps({"output": str(args.output), "identifier": manifest["identifier"]}))
