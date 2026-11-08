"""Export validated EPUB reading projections as deterministic Text-Fabric bundles."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from tf.fabric import Fabric


class ConversionError(ValueError):
    """Input or projected graph cannot be exported faithfully."""


def _json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _write_graph(documents: list[dict[str, Any]], destination: Path) -> dict[str, Any]:
    node: dict[str, dict[int, Any]] = defaultdict(dict)
    edge: dict[str, dict[int, set[int]]] = defaultdict(dict)
    specs: list[tuple[str, list[int], dict[str, Any], str | None]] = []
    lookup: dict[str, int] = {}
    slot = 0
    for document in documents:
        start = slot
        for char in document["text"]:
            slot += 1
            node["otype"][slot] = "character"
            node["text"][slot] = char
        if slot == start:
            raise ConversionError(f"Empty reading spine item: {document['member']}")
        doc_key = "document:" + document["id"]
        specs.append(
            (
                doc_key,
                list(range(start + 1, slot + 1)),
                {"document": document["id"], "source_member": document["member"]},
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
                    key,
                    list(range(start + element["start"] + 1, start + element["end"] + 1)),
                    {
                        "xhtml_tag": element["tag"],
                        "attributes": json.dumps(
                            element["attributes"], ensure_ascii=False, sort_keys=True
                        ),
                        "source_member": document["member"],
                        "start": element["start"],
                        "end": element["end"],
                    },
                    parent,
                )
            )
    # TF requires one contiguous node block per type.
    for kind in ("document", "element"):
        for key, slots, features, parent in specs:
            if (parent is None) != (kind == "document"):
                continue
            number = len(node["otype"]) + 1
            lookup[key] = number
            node["otype"][number] = kind
            edge["oslots"][number] = set(slots)
            for name, value in features.items():
                node[name][number] = value
    for key, _, _, parent in specs:
        if parent and key in lookup and parent in lookup:
            edge["parent"][lookup[key]] = {lookup[parent]}
    meta: dict[str, dict[str, str]] = {
        name: {"valueType": "int" if name in {"start", "end"} else "str"} for name in node
    }
    meta.update({name: {"valueType": "str"} for name in edge})
    meta[""] = {"converter": "corpora-epub-to-tf", "slotPolicy": "Unicode scalar; no normalization"}
    meta["otext"] = {
        "fmt:text-orig-full": "{text}",
        "sectionTypes": "document",
        "sectionFeatures": "document",
    }
    destination.mkdir()
    if not Fabric(locations=str(destination), silent="deep").save(
        nodeFeatures=dict(node), edgeFeatures=dict(edge), metaData=meta, silent="deep"
    ):
        raise ConversionError("Text-Fabric writer rejected projected graph")
    for path in destination.glob("*.tf"):
        header, data = path.read_text(encoding="utf-8").split("\n\n", 1)
        header = "\n".join(
            line for line in header.splitlines() if not line.startswith("@dateWritten=")
        )
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


def convert(source: Path, output: Path, checker: Path) -> dict[str, Any]:
    """Validate and export one local EPUB; existing destinations are never overwritten."""
    source = source.absolute()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ConversionError(f"Output already exists: {output}")
    original = source.read_bytes()
    checked = subprocess.run(
        [str(checker), str(source)], capture_output=True, text=True, check=False
    )
    if checked.returncode not in {0, 1}:
        raise ConversionError(checked.stderr.strip() or "EPUB checker failed")
    report: dict[str, Any] = json.loads(checked.stdout)
    if report["archive_sha256"] != hashlib.sha256(original).hexdigest():
        raise ConversionError("EPUB changed between validation and export")
    if checked.returncode or not report["documents"]:
        findings = [
            f"{item['member']}: {diagnostic['code']}: {diagnostic['message']}"
            for item in report["findings"]
            for diagnostic in item["report"]["diagnostics"]
            if diagnostic["blocking"]
        ]
        raise ConversionError("EPUB validation blocked export: " + "; ".join(findings))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (stage / "sources").mkdir()
        (stage / "sources" / "original.epub").write_bytes(original)
        (stage / "documents").mkdir()
        for index, document in enumerate(report["documents"], 1):
            _json(stage / "documents" / f"{index:04}.json", document)
            (stage / "documents" / f"{index:04}.txt").write_text(document["text"], encoding="utf-8")
        graph = _write_graph(report["documents"], stage / "tf")
        api = Fabric(locations=str(stage / "tf"), silent="deep").load(
            "text document source_member xhtml_tag", silent="deep"
        )
        if api is False:
            raise ConversionError("Real Text-Fabric loader rejected export")
        for document in report["documents"]:
            node = graph["node_ids"]["document:" + document["id"]]
            if api.T.text(node) != document["text"]:
                raise ConversionError(f"Text round-trip failed: {document['member']}")
        for path in (stage / "tf").iterdir():
            if path.is_dir():
                shutil.rmtree(path)
        manifest = {
            "format": "corpora-epub-to-tf/1",
            "source": {"sha256": report["archive_sha256"], "file": "sources/original.epub"},
            "members": report["members"],
            "identifier": report["identifier"],
            "metadata": report["metadata"],
            "navigation": report["navigation"],
            "documents": [doc["id"] for doc in report["documents"]],
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
    args = parser.parse_args()
    try:
        manifest = convert(args.source, args.output, args.checker)
    except ConversionError as error:
        parser.error(str(error))
    print(json.dumps({"output": str(args.output), "identifier": manifest["identifier"]}))
