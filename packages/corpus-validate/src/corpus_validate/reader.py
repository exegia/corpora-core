"""Read-only views over validated corpus archives using Context-Fabric."""

from __future__ import annotations

import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Literal

import yaml

from .validator import (
    MAX_ARCHIVE_BYTES,
    ArchiveTooLarge,
    _extract,
    _members,
    _preflight_node_limit,
)

View = Literal["manifest", "index", "sections", "content", "node", "versions"]


class ArchiveReadNotFound(ValueError):
    """A requested manifest, section reference, or node is absent."""


def _tf_root(root: Path) -> Path | None:
    datasets = list(root.rglob("otype.tf"))
    if not datasets:
        return None
    if len(datasets) != 1:
        raise ValueError("Archive must contain exactly one Text-Fabric otype.tf")
    return datasets[0].parent


def _load_api(root: Path) -> Any | None:
    tf_root = _tf_root(root)
    if tf_root is None:
        return None
    _preflight_node_limit(tf_root)
    from cfabric import Fabric

    fabric = Fabric(locations=str(tf_root), silent="deep")
    caches = sorted(path for path in (tf_root / ".cfr").rglob("*.cfr") if path.is_file())
    if caches:
        if len(caches) != 1:
            raise ValueError("Archive must contain exactly one Context-Fabric .cfr cache")
        api = fabric.openMapped(str(caches[0]))
    else:
        api = fabric.loadAll(silent="deep")
    if not api:
        raise ValueError("Context-Fabric could not load the corpus")
    return api


def _section_ref(api: Any, node: int) -> str:
    try:
        parts = api.T.sectionFromNode(node)
        ref = " ".join(str(part) for part in parts if part is not None)
        return ref or str(node)
    except Exception:
        return str(node)


def _slot_span(api: Any, node: int) -> int | None:
    otype = api.F.otype.v(node)
    if otype is None:
        return None
    if otype == api.F.otype.slotType:
        return 1
    try:
        slots = api.E.oslots.s(node)
    except Exception:
        return None
    return int(slots[-1]) - int(slots[0]) + 1 if slots else None


def _section_label(api: Any, node: int) -> str:
    try:
        labels = [str(part) for part in api.T.sectionFromNode(node) if part is not None]
        if labels:
            return labels[-1]
    except Exception:
        pass
    return str(node)


def _section_entry(api: Any, node: int, grandchild_type: str | None = None) -> dict[str, Any]:
    child_count = len(list(api.L.d(node, otype=grandchild_type))) if grandchild_type else 0
    ref = _section_ref(api, node)
    return {
        "title": _section_label(api, node) or ref,
        "ref": ref,
        "otype": str(api.F.otype.v(node) or ""),
        "child_count": child_count,
        "nodes": child_count,
        "words": _slot_span(api, node),
    }


def _section_levels(api: Any) -> list[str]:
    try:
        return list(api.T.sectionTypes)
    except Exception:
        return []


def _parse_ref(ref: str, api: Any) -> tuple[Any, ...] | None:
    ref = ref.strip()
    try:
        count = len(api.T.sectionTypes)
    except Exception:
        count = 3
    if count <= 1:
        return (ref,)
    if ":" in ref:
        head, last = ref.rsplit(":", 1)
        parts = head.split()
        try:
            if len(parts) > 1:
                return (" ".join(parts[:-1]), int(parts[-1]), int(last))
            return (parts[0], int(last)) if parts else None
        except ValueError:
            return None
    parts = ref.split()
    if len(parts) > 1:
        try:
            return (" ".join(parts[:-1]), int(parts[-1]))
        except ValueError:
            pass
    return (ref,)


def _resolve_ref(api: Any, ref: str, levels: list[str]) -> int | None:
    parts = _parse_ref(ref, api)
    if parts is not None:
        try:
            node = api.T.nodeFromSection(parts)
        except Exception:
            node = None
        if node is not None:
            return int(node)
    for otype in levels:
        for node in api.F.otype.s(otype):
            if _section_ref(api, node) == ref.strip():
                return int(node)
    return None


def _node_type_stats(api: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    slot_type = api.F.otype.slotType
    for otype in api.F.otype.all or ():
        nodes = list(api.F.otype.s(otype))
        spans = [span for node in nodes if (span := _slot_span(api, node)) is not None]
        avg = 1.0 if otype == slot_type else (sum(spans) / len(spans) if spans else 0.0)
        rows.append(
            {
                "type": otype,
                "count": len(nodes),
                "avg_slots": round(avg, 1),
                "is_slot": otype == slot_type,
            }
        )
    return rows


def _build_sections(api: Any) -> dict[str, Any] | None:
    levels = _section_levels(api)
    if not levels:
        return None
    top_type = levels[0]
    child_type = levels[1] if len(levels) > 1 else None
    grandchild_type = levels[2] if len(levels) > 2 else None
    items = []
    for node in api.F.otype.s(top_type):
        children = list(api.L.d(node, otype=child_type)) if child_type else []
        item = _section_entry(api, node, child_type)
        item["children"] = [
            {**_section_entry(api, child, grandchild_type)} for child in children[:500]
        ]
        item["truncated"] = len(children) > 500
        items.append(item)
    return {"levels": levels, "items": items}


def _sections(api: Any | None, parent: str | None, offset: int, limit: int) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    empty = {
        "parent": parent,
        "levels": [],
        "items": [],
        "total": 0,
        "offset": offset,
        "limit": limit,
        "next_offset": None,
    }
    if api is None:
        return empty
    levels = _section_levels(api)
    if not levels:
        return {**empty, "levels": levels}
    if parent:
        node = _resolve_ref(api, parent, levels)
        if node is None:
            raise ArchiveReadNotFound(f"Section reference {parent!r} not found")
        otype = api.F.otype.v(node)
        index = levels.index(otype) if otype in levels else -1
        child_type = levels[index + 1] if 0 <= index < len(levels) - 1 else None
        grandchild_type = levels[index + 2] if 0 <= index < len(levels) - 2 else None
        nodes = list(api.L.d(node, otype=child_type)) if child_type else []
    else:
        child_type = levels[0]
        grandchild_type = levels[1] if len(levels) > 1 else None
        nodes = list(api.F.otype.s(child_type))
    total = len(nodes)
    next_offset = offset + limit if offset + limit < total else None
    return {
        "parent": parent,
        "levels": levels,
        "items": [
            _section_entry(api, node, grandchild_type) for node in nodes[offset : offset + limit]
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
    }


def _finest_otype(api: Any) -> str:
    types = list(api.F.otype.all or ())
    slot = api.F.otype.slotType
    non_slot = [otype for otype in types if otype != slot]
    return non_slot[-1] if non_slot else slot


def _passage_nodes(api: Any, section_node: int | None, levels: list[str]) -> list[int]:
    lowest = levels[-1] if levels else None
    if len(levels) == 1:
        # Use finer passages only when they partition the source slots exactly.
        finest = _finest_otype(api)
        candidates = list(
            api.F.otype.s(finest) if section_node is None else api.L.d(section_node, otype=finest)
        )
        remaining = set(
            range(1, api.F.otype.maxSlot + 1)
            if section_node is None
            else api.E.oslots.s(section_node)
        )
        if candidates and remaining:
            for node in candidates:
                slots = (node,) if finest == api.F.otype.slotType else api.E.oslots.s(node)
                if not remaining.issuperset(slots):
                    break
                remaining.difference_update(slots)
            else:
                if not remaining:
                    return candidates
    if section_node is None:
        if lowest is not None:
            return list(api.F.otype.s(lowest))
        return list(api.F.otype.s(_finest_otype(api)))
    node_type = api.F.otype.v(section_node)
    index = levels.index(node_type) if node_type in levels else 0
    if lowest is not None and node_type == lowest:
        return [section_node]
    if levels and index < len(levels) - 1 and lowest is not None:
        nodes = list(api.L.d(section_node, otype=lowest))
        if nodes:
            return nodes
    nodes = list(api.L.d(section_node, otype=_finest_otype(api)))
    return nodes if nodes else [section_node]


def _feature_names(api: Any) -> set[str]:
    try:
        return set(api.Fall())
    except Exception:
        return set()


def _slot_tokens(api: Any, node: int, fmt: str, *, default_format: bool) -> list[dict[str, Any]]:
    slot_type = api.F.otype.slotType
    slots = (
        [node] if api.F.otype.v(node) == slot_type else list(api.L.d(node, otype=slot_type) or ())
    )
    names = _feature_names(api)
    tokens = []
    for slot in slots:
        text = ""
        try:
            raw = api.T.text(slot, fmt=fmt) if fmt else api.T.text(slot)
            text = str(raw) if raw is not None else ""
        except Exception:
            pass
        after = ""
        if "after" in names:
            try:
                raw = api.Fs("after").v(slot)
                after = "" if raw is None else str(raw)
            except Exception:
                pass
        if default_format and after and "text" in names:
            try:
                raw = api.Fs("text").v(slot)
                raw_text = str(raw) if raw is not None else ""
                if raw_text and text == raw_text + after:
                    text = raw_text
            except Exception:
                pass
        tokens.append({"text": text, "after": after, "node": int(slot)})
    return tokens


def _content(
    api: Any | None, ref: str | None, fmt: str | None, offset: int, limit: int
) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    if api is None:
        return {
            "ref": ref,
            "format": fmt or "",
            "passages": [],
            "total": 0,
            "offset": offset,
            "limit": limit,
            "next_offset": None,
        }
    try:
        format_used = fmt or api.T.defaultFormat
    except Exception:
        format_used = fmt or ""
    levels = _section_levels(api)
    section_node = None
    if ref:
        section_node = _resolve_ref(api, ref, levels)
        if section_node is None:
            raise ArchiveReadNotFound(f"Section reference {ref!r} not found")
    nodes = _passage_nodes(api, section_node, levels)
    total = len(nodes)
    passages = []
    for node in nodes[offset : offset + limit]:
        try:
            text = api.T.text(node, fmt=format_used) if format_used else api.T.text(node)
        except Exception:
            text = ""
        passages.append(
            {
                "node": int(node),
                "ref": _section_ref(api, node),
                "text": text,
                "tokens": _slot_tokens(api, node, format_used, default_format=not fmt),
            }
        )
    next_offset = offset + limit if offset + limit < total else None
    return {
        "ref": ref,
        "format": format_used,
        "passages": passages,
        "total": total,
        "offset": offset,
        "limit": limit,
        "next_offset": next_offset,
    }


def _node(api: Any, root: Path, node: int) -> dict[str, Any]:
    otype = api.F.otype.v(node)
    if otype is None:
        raise ArchiveReadNotFound(f"Node {node} not found")
    slot_type = api.F.otype.slotType
    is_slot = otype == slot_type
    if is_slot:
        first_slot = last_slot = int(node)
    else:
        try:
            slots = api.E.oslots.s(node)
            first_slot = int(slots[0]) if slots else None
            last_slot = int(slots[-1]) if slots else None
        except Exception:
            first_slot = last_slot = None
    features = {}
    for name in sorted(api.Fall()):
        if name == "otype":
            continue
        try:
            value = api.Fs(name).v(node)
        except Exception:
            continue
        if value is not None:
            features[name] = value
    try:
        text = api.T.text(node)
    except Exception:
        text = ""
    annotation = {}
    try:
        value = json.loads((root / "annotations.json").read_text())
        if isinstance(value, dict):
            annotation = value
    except (OSError, json.JSONDecodeError):
        pass
    annotations = annotation.get("nodes", {}).get(str(node))
    parents = []
    try:
        for parent in api.L.u(node) or ():
            parents.append(
                {
                    "node": int(parent),
                    "otype": str(api.F.otype.v(parent) or ""),
                    "ref": _section_ref(api, parent),
                }
            )
    except Exception:
        pass
    identity = None
    identity_feature = None
    names = _feature_names(api)
    for feature in ("lemma", "lex", "word", "form", "text"):
        if feature in names:
            try:
                value = api.Fs(feature).v(node)
            except Exception:
                continue
            if value is not None and str(value).strip():
                identity_feature, identity = feature, str(value)
                break
    if identity is None:
        identity = text if text and str(text).strip() else None
    corpus_count = section_count = 0
    if identity is not None:
        section_ref = _section_ref(api, node)
        for other in api.F.otype.s(otype):
            try:
                value = api.Fs(identity_feature).v(other) if identity_feature else api.T.text(other)
            except Exception:
                continue
            if value is not None and str(value) == identity:
                corpus_count += 1
                section_count += _section_ref(api, other) == section_ref
    return {
        "node": int(node),
        "otype": otype,
        "is_slot": is_slot,
        "slot_type": slot_type,
        "first_slot": first_slot,
        "last_slot": last_slot,
        "section_ref": _section_ref(api, node),
        "text": text,
        "features": features,
        "annotation": annotations,
        "node_types": [str(value) for value in (api.F.otype.all or ())],
        "context": parents,
        "occurrences": corpus_count,
        "occurrences_in_section": section_count,
    }


def _read(view: View, root: Path, **kwargs: Any) -> dict[str, Any]:
    if view == "versions":
        history = root / "history.yml"
        if history.is_file():
            try:
                data = yaml.safe_load(history.read_text()) or {}
            except (UnicodeDecodeError, yaml.YAMLError):
                data = {}
            versions = data.get("versions") if isinstance(data, dict) else None
            if isinstance(versions, list) and versions:
                return {"versions": versions}
        manifest_path = root / "manifest.yml"
        manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.is_file() else {}
        if not isinstance(manifest, dict):
            manifest = {}
        name = manifest.get("name")
        return {
            "versions": [
                {
                    "id": "packaged",
                    "sha": None,
                    "label": str(manifest.get("version") or "v1.0"),
                    "title": "Converted",
                    "at": str(manifest.get("written_date") or ""),
                    "current": True,
                    "notes": [str(name)] if name else [],
                }
            ]
        }
    if view == "manifest":
        path = root / "manifest.yml"
        if not path.is_file():
            raise ArchiveReadNotFound("No manifest.yml in corpus archive")
        data = yaml.safe_load(path.read_text())
        return data if isinstance(data, dict) else {}
    if view == "index":
        toc_path = root / "toc.yml"
        toc = yaml.safe_load(toc_path.read_text()) if toc_path.is_file() else None
        api = _load_api(root)
        return {
            "toc": toc,
            "sections": _build_sections(api) if api else None,
            "node_types": _node_type_stats(api) if api else [],
        }
    api = _load_api(root)
    if view == "sections":
        return _sections(
            api, kwargs.get("parent"), kwargs.get("offset", 0), kwargs.get("limit", 50)
        )
    if view == "content":
        return _content(
            api,
            kwargs.get("ref"),
            kwargs.get("fmt"),
            kwargs.get("offset", 0),
            kwargs.get("limit", 50),
        )
    if view == "node":
        if api is None:
            raise ArchiveReadNotFound("Corpus has no Text-Fabric data")
        return _node(api, root, int(kwargs["node"]))
    raise ValueError(f"Unsupported corpus view: {view}")


def read_archive(data: bytes, view: View, **kwargs: Any) -> dict[str, Any]:
    """Read one manifest/index/sections/content/node/versions view from a corpus ZIP.

    Each call extracts into a private temporary directory and opens a shipped
    Context-Fabric cache directly when present. No cross-request cache is kept,
    so caller identity and archive bytes cannot bleed between requests.
    """
    if not isinstance(data, bytes):
        raise TypeError("archive data must be bytes")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ArchiveTooLarge(f"Archive exceeds {MAX_ARCHIVE_BYTES} bytes")
    if view not in {"manifest", "index", "sections", "content", "node", "versions"}:
        raise ValueError(f"Unsupported corpus view: {view}")
    with (
        zipfile.ZipFile(io.BytesIO(data)) as archive,
        tempfile.TemporaryDirectory(prefix="corpus-read-") as temporary,
    ):
        infos = _members(archive)
        root = Path(temporary)
        _extract(archive, infos, root)
        return _read(view, root, **kwargs)
