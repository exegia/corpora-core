"""Reference operations over a bounded, caller-selected corpus archive."""

from __future__ import annotations

import io
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

from . import refcompact, refdisplay, tfref
from .reader import ArchiveReadNotFound, _load_api
from .validator import MAX_ARCHIVE_BYTES, ArchiveTooLarge, _extract, _members


def _payload(adapter: tfref.Adapter, ref: tfref.Ref, nodes: int | list[int]) -> dict[str, Any]:
    values = nodes if isinstance(nodes, list) else [nodes]
    first, last = values[0], values[-1]
    lo, _ = adapter.slots(first)
    _, hi = adapter.slots(last)
    return {
        "node": first,
        "nodes": values,
        "is_range": len(values) > 1,
        "otype": adapter.otype(first),
        "sections": refdisplay.sections_dict(adapter, ref.sections),
        "section_types": list(adapter.section_types),
        "first_slot": lo,
        "last_slot": hi,
        "text": " ".join(text for n in values if (text := adapter.text(n))),
    }


def reference_archive(
    data: bytes,
    corpus_id: str,
    *,
    node: int | None = None,
    end_node: int | None = None,
    ref: str | None = None,
    lang: str | None = None,
    shortcode: bool = False,
    url_template: str | None = None,
) -> dict[str, Any]:
    """Create or resolve a reference using only the supplied archive bytes."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge(f"Archive exceeds {MAX_ARCHIVE_BYTES} bytes")
    with (
        zipfile.ZipFile(io.BytesIO(data)) as archive,
        tempfile.TemporaryDirectory(prefix="corpus-reference-") as temporary,
    ):
        root = Path(temporary)
        _extract(archive, _members(archive), root)
        api = _load_api(root)
        if api is None:
            raise ArchiveReadNotFound("Corpus has no Text-Fabric data")
        manifest_path, toc_path = root / "manifest.yml", root / "toc.yml"
        manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.is_file() else {}
        toc = yaml.safe_load(toc_path.read_text()) if toc_path.is_file() else {}
        manifest = manifest if isinstance(manifest, dict) else {}
        toc = toc if isinstance(toc, dict) else {}
        adapter = tfref.load_corpus(api, version=str(manifest.get("version") or "") or None)
        original = ref
        if ref is not None:
            if refcompact.is_compact(ref):
                if refcompact.slug_of(ref) != refcompact.corpus_slug(corpus_id):
                    raise tfref.ParseError("Reference corpus does not match the selected archive")
                _, target = refcompact.from_compact(ref, adapter)
            else:
                parsed_input = tfref.parse(ref)
                if parsed_input.corpus and parsed_input.corpus != corpus_id:
                    raise tfref.ParseError("Reference corpus does not match the selected archive")
                target = tfref.resolve(parsed_input, adapter, lang=lang)
        elif node is not None:
            target = [node, end_node] if end_node is not None and end_node != node else node
        else:
            raise tfref.ParseError("A reference or node is required")
        if isinstance(target, list):
            target = [target[0], target[-1]] if len(target) > 1 else target[0]
        canonical = tfref.serialize(target, adapter, corpus_id=corpus_id, lang=lang)
        parsed = tfref.parse(canonical)
        nodes = tfref.resolve(parsed, adapter, lang=lang)
        try:
            token = refcompact.to_compact(target, adapter, corpus_id)
        except tfref.RefError:
            token = None
        if shortcode:
            return refdisplay.shortcode_payload(
                parsed, canonical, url_template=url_template, token=token
            )
        result = _payload(adapter, parsed, nodes)
        result.update(
            ref=canonical,
            urn=parsed.urn(),
            token=token,
            corpus=refdisplay.corpus_metadata(
                corpus_id=corpus_id, manifest=manifest, toc=toc, version=adapter.version
            ),
        )
        if original is not None:
            result["input"] = original
        return result
