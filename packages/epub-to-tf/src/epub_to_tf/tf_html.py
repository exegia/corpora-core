"""Render the retained XHTML reading tree from a loaded Text-Fabric graph.

This is a semantic QA view, not an EPUB stylesheet or a byte-for-byte XHTML
round trip. The original archive remains the authority for both.
"""

import html
import json
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from tf.fabric import Fabric

TAGS = frozenset(
    "body article section aside main header footer nav div p h1 h2 h3 h4 h5 h6 "
    "span em strong b i u s small sub sup mark q cite abbr time a blockquote "
    "pre code kbd samp var ruby rt rp bdi bdo wbr dfn del ins data address hgroup "
    "ol ul li dl dt dd table caption thead tbody tfoot tr th td details summary "
    "figure figcaption br hr img audio video source track object embed".split()
)
VOID = frozenset({"br", "hr", "img", "source", "track", "wbr", "embed"})
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
MATH_NS = "http://www.w3.org/1998/Math/MathML"


def _asset_path(asset: dict[str, Any]) -> str:
    file_name = str(asset["file"])
    path = PurePosixPath(file_name)
    if path.parts[:2] != ("tf", "assets") or ".." in path.parts:
        raise ValueError(f"Unsafe TF asset path: {file_name}")
    return "../" + file_name


def _math_markup(bundle: Path, asset: dict[str, Any]) -> str:
    """Embed passive MathML while retaining the exact source asset separately."""
    source = (bundle / asset["file"]).read_bytes()
    if b"<!DOCTYPE" in source.upper() or b"<!ENTITY" in source.upper():
        raise ValueError("Inline MathML contains a DTD or entity declaration")
    root = ET.fromstring(source)

    def element(node: ET.Element, root_element: bool = False) -> str:
        if not isinstance(node.tag, str) or not node.tag.startswith("{" + MATH_NS + "}"):
            raise ValueError("Inline MathML contains a foreign-namespace element")
        tag = node.tag.split("}", 1)[1]
        if not tag.replace("-", "").isalnum():
            raise ValueError("Inline MathML contains an invalid element name")
        attrs = []
        for key, value in node.attrib.items():
            if (
                "}" in key
                or key.lower().startswith("on")
                or key.lower() in {"href", "src", "style", "action", "formaction", "target"}
            ):
                continue
            attrs.append(f' {key}="{html.escape(value, quote=True)}"')
        if root_element:
            asset_file = html.escape(str(asset["file"]), quote=True)
            attrs.append(f' xmlns="{MATH_NS}" data-tf-asset="{asset_file}"')
        body = [html.escape(node.text or "")]
        for child in node:
            body.append(element(child))
            body.append(html.escape(child.tail or ""))
        return f"<{tag}{''.join(attrs)}>{''.join(body)}</{tag}>"

    return element(root, True)


def _attributes(tag: str, source: dict[str, str], assets: list[dict[str, Any]]) -> str:
    values = {key: value for key, value in source.items() if key in ATTRS}
    if "type" in source:
        values["data-epub-type"] = source["type"]
    if tag == "a" and source.get("href", "").startswith("#"):
        values["href"] = source["href"]
    elif tag == "a" and "href" in source:
        values["data-source-href"] = source["href"]
    for asset in assets:
        path = _asset_path(asset)
        if tag == "video" and asset["kind"] == "image":
            values["poster"] = path
        elif tag == "object" and asset["kind"] == "object":
            values["data"] = path
        elif tag in {"img", "audio", "video", "source", "track", "embed"}:
            values["src"] = path
    return "".join(
        f' {key}="{html.escape(str(value), quote=True)}"' for key, value in sorted(values.items())
    )


def _render_scope(
    api: Any,
    bundle: Path,
    root: int,
    scope_id: str,
    root_tag: str,
    children: dict[int, list[int]],
    assets: dict[tuple[str, str], list[dict[str, Any]]],
    key_for_node: dict[int, str],
) -> str:
    reading = api.T.text(root)

    def element(node: int, start: int, end: int) -> str:
        tag = api.F.xhtml_tag.v(node) if node != root else root_tag
        source_body = tag == "body"
        if source_body:
            tag = "div"
        attrs = json.loads(api.F.attributes.v(node)) if node != root else {}
        node_key = key_for_node.get(node, "").rsplit(":", 1)[-1]
        element_assets = assets.get((scope_id, node_key), [])
        if tag == "math":
            math = next((asset for asset in element_assets if asset["kind"] == "math"), None)
            if math:
                return _math_markup(bundle, math)
        if tag == "svg":
            svg = next(
                (asset for asset in element_assets if asset["media_type"] == "image/svg+xml"),
                None,
            )
            if svg:
                path = html.escape(_asset_path(svg), quote=True)
                return f'<img src="{path}" data-source-tag="svg" alt="Inline SVG">'
        if tag not in TAGS:
            original_tag = tag
            tag = "span"
        else:
            original_tag = None
        opening = (
            "<"
            + tag
            + _attributes(tag, attrs, element_assets)
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
    with tempfile.TemporaryDirectory(prefix="epub-tf-qa-") as temporary:
        tf_copy = Path(temporary)
        for source in (bundle / "tf").glob("*.tf"):
            if source.is_file():
                shutil.copyfile(source, tf_copy / source.name)
        api = Fabric(locations=str(tf_copy), silent="deep").load(
            "text reading document xhtml_tag attributes reading_start reading_end "
            "source_byte empty_element asset_refs parent",
            silent="deep",
        )
        if not api:
            raise ValueError("Text-Fabric could not load the semantic graph")
        _render_loaded(api, bundle, output, manifest)


def _render_loaded(api: Any, bundle: Path, output: Path, manifest: dict[str, Any]) -> None:
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

    assets: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    allowed_assets = {asset["file"] for asset in manifest["assets"]}
    for scope_key in ["document:" + item_id for item_id in manifest["documents"]] + [
        "note:" + note_key for note_key in manifest["notes"]
    ]:
        scope_node = node_ids[scope_key]
        for asset in json.loads(api.F.asset_refs.v(scope_node)):
            if asset["file"] not in allowed_assets:
                raise ValueError(f"TF references an unexported asset: {asset['file']}")
            assets[(asset["scope_id"], asset["element_key"])].append(asset)
    notes_by_document: dict[str, list[str]] = defaultdict(list)
    for reference in manifest["note_references"]:
        notes = notes_by_document[reference["document_id"]]
        if reference["target_key"] not in notes:
            notes.append(reference["target_key"])
    rendered = output / "tf-rendered"
    rendered.mkdir(exist_ok=True)
    for index, item_id in enumerate(manifest["documents"], 1):
        root = node_ids["document:" + item_id]
        content = _render_scope(api, bundle, root, item_id, "main", children, assets, key_for_node)
        for note_key in notes_by_document[item_id]:
            note_root = node_ids["note:" + note_key]
            content += _render_scope(
                api, bundle, note_root, note_key, "div", children, assets, key_for_node
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
