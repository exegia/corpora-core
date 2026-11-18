"""Rewrite a text span while retaining valid Text-Fabric graph structure."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tf.fabric import Fabric

from .validator import MAX_NODES, _plain


def replace_node_text(
    root: Path, tf_root: Path, api: Any, node: int, feature: str, text: str
) -> tuple[set[str], int, tuple[int, ...], dict[str, bytes]]:
    """Retokenize a contiguous span, remap the graph and return changed feature names.

    Ambiguous cross-boundary edges and annotations are rejected rather than moved
    to a guessed target. A caller must rebuild and validate the Context-Fabric cache.
    """
    if not isinstance(feature, str) or feature not in set(api.Fall()) - {"otype"}:
        raise ValueError("Text feature is unavailable")
    if type(text) is not str:
        raise ValueError("Replacement text must be a string")
    text_feature = api.Fs(feature)
    if text_feature.meta.get("valueType") != "str":
        raise ValueError("Text feature must contain strings")
    config = api.TF.features.get("otext")
    default_format = api.T.defaultFormat
    template = (
        config.metaData.get("fmt:" + default_format)
        if config and isinstance(default_format, str)
        else None
    )
    if template != "{" + feature + "}":
        raise ValueError("Default text format must use exactly the selected text feature")
    max_slot, max_node = int(api.F.otype.maxSlot), int(api.F.otype.maxNode)
    slots = [node] if node <= max_slot else [int(n) for n in api.E.oslots.s(node)]
    if not slots or slots != list(range(slots[0], slots[-1] + 1)):
        raise ValueError("Node text must span contiguous slots")
    original = "".join(text_feature.v(slot) or "" for slot in slots)
    if api.T.text(node) != original:
        raise ValueError("Default text cannot be represented by the selected feature")
    words = (list(text) if api.F.otype.slotType == "char" else re.findall(r"\s*\S+\s*", text)) or [
        text
    ]
    first, last = slots[0], slots[-1]
    delta = len(words) - len(slots)
    if max_node + delta > MAX_NODES:
        raise ValueError("Edited corpus exceeds the node limit")
    removed = set(range(first + len(words), last + 1)) if delta < 0 else set()
    if delta:
        annotations = root / "annotations.json"
        if annotations.exists():
            data = json.loads(annotations.read_bytes())
            if data not in ({}, {"nodes": {}}):
                raise ValueError("Renumbering nodes with annotations is unsupported")

    def remap(n: int) -> int:
        n = int(n)
        if n in removed:
            raise ValueError("A removed word has retained data or links")
        return n + delta if n > last else n

    extra: dict[str, bytes] = {}
    if delta:
        # Converter manifests can carry node IDs alongside the TF graph.
        manifest_paths = {root / "manifest.json", tf_root.parent / "manifest.json"}
        for manifest in manifest_paths:
            if not manifest.is_file():
                continue
            document = json.loads(manifest.read_bytes())
            if not isinstance(document, dict):
                raise ValueError("Converter manifest is invalid")
            graph = document.get("graph")
            if graph is None:
                continue
            if (
                not isinstance(graph, dict)
                or type(graph.get("max_slot")) is not int
                or type(graph.get("max_node")) is not int
                or graph.get("max_slot") != max_slot
                or graph.get("max_node") != max_node
                or not isinstance(graph.get("node_ids"), dict)
            ):
                raise ValueError("Converter manifest graph does not match Text-Fabric")
            identifiers = graph["node_ids"]
            if any(
                not isinstance(key, str) or type(value) is not int or not 1 <= value <= max_node
                for key, value in identifiers.items()
            ):
                raise ValueError("Converter manifest node IDs are invalid")
            graph["node_ids"] = {key: remap(value) for key, value in identifiers.items()}
            graph["max_slot"], graph["max_node"] = max_slot + delta, max_node + delta
            extra[manifest.relative_to(root).as_posix()] = (
                json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
    node_features: dict[str, dict[int, Any]] = {}
    edge_features: dict[str, dict[int, Any]] = {}
    metadata: dict[str, dict[str, str]] = {}
    for name in api.Fall():
        feature_api = api.Fs(name)
        values = {}
        for old, value in feature_api.items():
            old = int(old)
            if name == feature and first <= old <= last:
                continue
            if delta and name != "otype" and first <= old <= last:
                raise ValueError("Retokenization would make word attributes ambiguous")
            if old in removed and name == "otype":
                continue
            values[remap(old)] = _plain(value)
        if name == "otype":
            for index in range(len(words)):
                values[first + index] = api.F.otype.slotType
        if name == feature:
            values.update({first + index: word for index, word in enumerate(words)})
        node_features[name] = values
        metadata[name] = dict(feature_api.meta)
    selected = set(slots)
    replacement = set(range(first, first + len(words)))
    for name in api.Eall():
        feature_api = api.Es(name)
        values = {}
        for source, targets in feature_api.items():
            source = int(source)
            mapped_source = remap(source)
            if (
                name != "oslots"
                and delta
                and (source in selected or any(int(n) in selected for n in targets))
            ):
                raise ValueError("Retokenization would make word links ambiguous")
            if isinstance(targets, dict):
                if name == "oslots":
                    raise ValueError("Unexpected valued structural links")
                values[mapped_source] = {
                    remap(target): _plain(value) for target, value in targets.items()
                }
            else:
                linked = {int(target) for target in targets}
                if name == "oslots" and linked & selected:
                    if selected <= linked:
                        # Replacement IDs are new; remap only original outside slots.
                        outside = linked - selected
                        values[mapped_source] = {remap(n) for n in outside} | replacement
                        continue
                    if delta:
                        raise ValueError("A nested node only partially overlaps the edited text")
                values[mapped_source] = {remap(target) for target in linked}
        edge_features[name] = values
        metadata[name] = dict(feature_api.meta)
    if not Fabric(locations=str(tf_root), silent="deep").save(
        nodeFeatures=node_features, edgeFeatures=edge_features, metaData=metadata, silent="deep"
    ):
        raise ValueError("Could not save the edited Text-Fabric graph")
    return set(node_features) | set(edge_features), remap(node), tuple(sorted(replacement)), extra
