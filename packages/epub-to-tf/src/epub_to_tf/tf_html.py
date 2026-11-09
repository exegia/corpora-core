"""Render the retained XHTML reading tree from a loaded Text-Fabric graph.

This is a semantic QA view, not an EPUB stylesheet or a byte-for-byte XHTML
round trip. The original archive remains the authority for both.
"""

import html
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from tf.fabric import Fabric

TAGS = frozenset(
    "body article section aside main header footer nav div p h1 h2 h3 h4 h5 h6 "
    "span em strong b i u s small sub sup mark q cite abbr time a blockquote "
    "pre code kbd samp var ruby rt rp bdi bdo wbr dfn del ins data address hgroup "
    "ol ul li dl dt dd table caption thead tbody tfoot tr th td details summary "
    "figure figcaption br hr img audio video source track".split()
)
VOID = frozenset({"br", "hr", "img", "source", "track", "wbr"})
ATTRS = frozenset(
    {
        "id",
        "class",
        "title",
        "lang",
        "dir",
        "role",
        "alt",
        "scope",
        "colspan",
        "rowspan",
        "headers",
        "start",
        "value",
        "reversed",
        "datetime",
        "cite",
        "open",
        "controls",
        "width",
        "height",
    }
)


def _attributes(tag: str, source: dict[str, str], asset: dict[str, Any] | None) -> str:
    values = {key: value for key, value in source.items() if key in ATTRS}
    if "type" in source:
        values["data-epub-type"] = source["type"]
    if tag == "a" and source.get("href", "").startswith("#"):
        values["href"] = source["href"]
    elif tag == "a" and "href" in source:
        values["data-source-href"] = source["href"]
    if asset and tag in {"img", "audio", "video", "source"}:
        values["src"] = "../" + asset["file"]
    return "".join(
        f' {key}="{html.escape(str(value), quote=True)}"' for key, value in sorted(values.items())
    )


def _render_scope(
    api: Any,
    root: int,
    scope_id: str,
    root_tag: str,
    children: dict[int, list[int]],
    assets: dict[tuple[str, str], dict[str, Any]],
    key_for_node: dict[int, str],
) -> str:
    reading = api.T.text(root)

    def element(node: int, start: int, end: int) -> str:
        tag = api.F.xhtml_tag.v(node) if node != root else root_tag
        source_body = tag == "body"
        if source_body:
            tag = "div"
        if tag not in TAGS:
            original_tag = tag
            tag = "span"
        else:
            original_tag = None
        attrs = json.loads(api.F.attributes.v(node)) if node != root else {}
        node_key = key_for_node.get(node, "").rsplit(":", 1)[-1]
        asset = assets.get((scope_id, node_key))
        opening = (
            "<"
            + tag
            + _attributes(tag, attrs, asset)
            + (' data-source-tag="body"' if source_body else "")
            + (
                f' data-source-tag="{html.escape(original_tag, quote=True)}"'
                if original_tag
                else ""
            )
            + ">"
        )
        if tag in VOID:
            return opening
        pieces = [opening]
        cursor = start
        for child in children.get(node, []):
            child_start = api.F.reading_start.v(child)
            child_end = api.F.reading_end.v(child)
            if not start <= child_start <= child_end <= end or child_start < cursor:
                raise ValueError(f"Element {child} has inconsistent reading span")
            pieces.append(html.escape(reading[cursor:child_start]))
            pieces.append(element(child, child_start, child_end))
            cursor = child_end
        pieces.append(html.escape(reading[cursor:end]))
        pieces.append("</" + tag + ">")
        return "".join(pieces)

    return element(root, 0, len(reading))


def render_documents(bundle: Path, output: Path, manifest: dict[str, Any]) -> None:
    """Write one sandboxable HTML page per spine item, using loaded TF features."""
    api = Fabric(locations=str(bundle / "tf"), silent="deep").load(
        "text reading document xhtml_tag attributes reading_start reading_end "
        "source_byte empty_element parent",
        silent="deep",
    )
    if not api:
        raise ValueError("Text-Fabric could not load the semantic graph")
    node_ids = manifest["graph"]["node_ids"]
    key_for_node = {number: key for key, number in node_ids.items()}
    children: dict[int, list[int]] = defaultdict(list)
    for node in api.F.otype.s("element"):
        parents = api.E.parent.f(node)
        if len(parents) != 1:
            raise ValueError(f"Element {node} has no unique parent")
        children[parents[0]].append(node)
    for siblings in children.values():
        siblings.sort(key=lambda node: (api.F.reading_start.v(node), api.F.source_byte.v(node)))

    assets = {(asset["scope_id"], asset["element_key"]): asset for asset in manifest["assets"]}
    notes_by_document: dict[str, list[str]] = defaultdict(list)
    for reference in manifest["note_references"]:
        notes = notes_by_document[reference["document_id"]]
        if reference["target_key"] not in notes:
            notes.append(reference["target_key"])
    rendered = output / "tf-rendered"
    rendered.mkdir(exist_ok=True)
    for index, item_id in enumerate(manifest["documents"], 1):
        root = node_ids["document:" + item_id]
        content = _render_scope(api, root, item_id, "main", children, assets, key_for_node)
        for note_key in notes_by_document[item_id]:
            note_root = node_ids["note:" + note_key]
            content += _render_scope(
                api, note_root, note_key, "div", children, assets, key_for_node
            )
        page = (
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
            'img-src * data:; media-src *; style-src &#39;unsafe-inline&#39;">'
            "<style>:root{color-scheme:dark}body{font:16px/1.6 Georgia,serif;margin:24px;"
            "color:#e7edf6;background:#192231}main{white-space:pre-line}"
            "a{color:#9cc9ff}pre,code{white-space:pre-wrap}"
            "img,video{max-width:100%;height:auto}table{border-collapse:collapse}"
            "td,th{border:1px solid #607086;padding:.3em}</style>" + content + "</html>"
        )
        (rendered / f"{index:04}.html").write_text(page, encoding="utf-8")
