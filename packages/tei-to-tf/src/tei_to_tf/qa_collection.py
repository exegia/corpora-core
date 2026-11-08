"""Exhaustive collection QA and navigable, independently rendered TEI/TF views."""

# ruff: noqa: E501

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, cast

from cfabric.core import Fabric as ContextFabric
from lxml import etree
from tf.fabric import Fabric

from .acquire import acquire
from .convert import convert, write_json
from .model import ConversionError, Policy, Source
from .parse import TEI, parse, secure_tree
from .qa_baudelaire import STYLE, require
from .qa_quality import MARK_STYLE, PANEL, SCRIPT, attach_quality, marked_text
from .quality import structural_preview

URL = "https://github.com/CliffordAnderson/corpus-baudelaire/tree/master/fleurs-du-mal"
FEATURES = (
    "text tei_tag tei_namespace attributes source_path source start end "
    "parent document region block"
)
POLICY = Policy(choice="original", apparatus="lemma")


def oracle(data: bytes) -> dict[str, Any]:
    """Independent XML traversal, never using the converter's projected text or elements.

    This QA profile uses original spelling and lemma readings, keeping notes separate.
    It checks a single text/body; unsupported or ambiguous readings are reported.
    """
    tree = secure_tree(data)
    bodies = cast(list[etree._Element], tree.xpath("/t:TEI/t:text/t:body", namespaces={"t": TEI}))
    require(len(bodies) == 1, "QA oracle requires one TEI text/body")
    body = bodies[0]
    parent = body.getparent()
    require(parent is not None and len(parent) == 1, "QA oracle requires body-only reading regions")
    forbidden = {"titlePage", "docTitle", "docAuthor", "docImprint"}
    records: list[dict[str, Any]] = []
    pieces: list[str] = []
    position = 0

    def emit(value: str | None) -> None:
        nonlocal position
        if value:
            pieces.append(value)
            position += len(value)

    def visit(node: Any, parent: str | None) -> None:
        if not isinstance(node.tag, str):
            return
        tag = etree.QName(node).localname
        if node.tag == f"{{{TEI}}}note":
            return
        require(tag not in forbidden, f"QA oracle needs explicit policy for {tag}")
        require(
            node.get("type", "").lower()
            not in {"toc", "contents", "tableofcontents", "table-of-contents"},
            "QA oracle needs explicit TOC exclusion policy",
        )
        path = tree.getpath(node)
        row = {
            "path": path,
            "tag": tag,
            "namespace": etree.QName(node).namespace or "",
            "attributes": dict(node.attrib),
            "parent": parent,
            "start": position,
            "end": 0,
        }
        records.append(row)
        if node.tag in {f"{{{TEI}}}app", f"{{{TEI}}}choice"}:
            selector = "t:lem" if tag == "app" else "t:orig | t:sic | t:abbr"
            selected = node.xpath(selector, namespaces={"t": TEI})
            require(len(selected) == 1, f"Ambiguous {tag}: expected one selected reading")
            require(
                not (node.text or "").strip() and not any((c.tail or "").strip() for c in node),
                "Text between alternatives",
            )
            visit(selected[0], path)
        else:
            emit(node.text)
            for child in node:
                visit(child, path)
                emit(child.tail)
        row["end"] = position

    visit(body, None)
    text = "".join(pieces)
    heads = [r for r in records if r["tag"] == "head"]
    title = text[heads[0]["start"] : heads[0]["end"]].strip() if heads else "Untitled"
    return {"title": title, "text": text, "elements": records}


def verify_document(
    api: Any, node: int, expected: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, int]]:
    slots = tuple(api.E.oslots.s(node))
    text = expected["text"]
    require(api.T.text(node) == text, "Document text differs from independent XML")
    require(len(slots) == len(text), "Document slot count differs")
    require(
        all(
            api.F.text.v(s) == char and api.T.text(s) == char
            for s, char in zip(slots, text, strict=True)
        ),
        "Slot value/rendering differs from source scalar",
    )
    elements = api.L.d(node, otype="element")
    rows = []
    for n in elements:
        parents = api.E.parent.f(n)
        require(
            len(parents) <= 1 and all(p in elements for p in parents),
            "Invalid/cross-document parent",
        )
        start, end = api.F.start.v(n), api.F.end.v(n)
        require(0 <= start < end <= len(text), "Invalid element range")
        require(tuple(api.E.oslots.s(n)) == slots[start:end], "Element slot span differs")
        require(api.T.text(n) == text[start:end], "Element rendered text differs")
        rows.append(
            {
                "path": api.F.source_path.v(n),
                "tag": api.F.tei_tag.v(n),
                "namespace": api.F.tei_namespace.v(n),
                "attributes": json.loads(api.F.attributes.v(n)),
                "parent": api.F.source_path.v(parents[0]) if parents else None,
                "start": start,
                "end": end,
            }
        )
    wanted = [r for r in expected["elements"] if r["start"] < r["end"]]
    require(
        sorted(rows, key=lambda r: r["path"]) == sorted(wanted, key=lambda r: r["path"]),
        "Element inventory/attributes/parents differ from independent XML",
    )
    for n in api.L.d(node, otype="block"):
        require(api.T.nodeFromSection(api.T.sectionFromNode(n)) == n, "Section round trip failed")
    # Order by source offset and ancestor depth, using graph-derived paths for equal spans.
    rows.sort(key=lambda r: (r["start"], r["path"].count("/"), r["path"]))
    heads = [r for r in rows if r["tag"] == "head"]
    rendered = api.T.text(node)
    title = rendered[heads[0]["start"] : heads[0]["end"]].strip() if heads else "Untitled"
    proof = {
        "characters": len(slots),
        "whitespace_characters": sum(c.isspace() for c in text),
        "elements": len(rows),
        "zero_width_elements": len(expected["elements"]) - len(rows),
        "lines": sum(r["tag"] == "l" for r in rows),
        "stanzas": sum(r["tag"] == "lg" for r in rows),
    }
    return {"title": title, "text": rendered, "elements": rows}, proof


def render_reading(view: dict[str, Any], issues: list[dict[str, Any]] | None = None) -> str:
    """Render mixed content with source order; never inject XML names or attributes as HTML."""
    children: dict[str | None, list[dict[str, Any]]] = {}
    for row in view["elements"]:
        if row["start"] < row["end"]:
            children.setdefault(row["parent"], []).append(row)
    mapping = {
        "head": "h2",
        "div": "section",
        "lg": "section",
        "l": "div",
        "p": "p",
        "emph": "em",
        "hi": "em",
        "q": "q",
        "quote": "blockquote",
    }

    def render(row: dict[str, Any]) -> str:
        cursor = row["start"]
        parts = []
        for child in sorted(children.get(row["path"], []), key=lambda r: r["start"]):
            parts.append(marked_text(view["text"], cursor, child["start"], issues or []))
            parts.append(render(child))
            cursor = child["end"]
        parts.append(marked_text(view["text"], cursor, row["end"], issues or []))
        tag = mapping.get(row["tag"], "span")
        css = {"lg": "stanza", "l": "verse-line"}.get(row["tag"], "tei-element")
        return f'<{tag} class="{css}">{"".join(parts)}</{tag}>'

    return "".join(render(r) for r in children.get(None, []))


def reading_page(
    view: dict[str, Any],
    kind: str,
    proof: dict[str, Any],
    issues: list[dict[str, Any]] | None = None,
) -> str:
    legend = (
        f"<p>{len(issues)} findings underlined in this displayed version. Yellow: 20 · Orange: 60; red: 90. "
        "Hover or focus a word for suggestions. Metadata and excluded readings stay in the table.</p>"
        if issues is not None
        else ""
    )
    return f"""<!doctype html><html lang="fr"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(view["title"])} · {kind}</title><style>{STYLE}{MARK_STYLE}
article {{font:19px/1.7 Georgia,serif}} h2 {{font-size:24px}}
.verse-line {{white-space:pre-wrap}} .stanza {{display:block;margin:1.5em 0}}
header {{padding:14px 24px}} main {{margin:20px auto}}</style>
<header><span class="badge">{kind}</span> · <span class="status">Exact text and structure verified</span>
<p>{proof["characters"]:,} characters · {proof["lines"]} verse lines · {proof["stanzas"]} line groups</p></header>
<main>{legend}<article>{render_reading(view, issues)}</article><details><summary>Exact corpus text (including whitespace)</summary>
<pre>{html.escape(view["text"])}</pre></details><details><summary>Validation scope</summary>
<p>Reading policy: encoded lemma, original spelling; notes kept separately.
<a href="document.json" target="_blank">Metadata, notes, excluded variants and annotations</a>.</p>
<p>All characters, nonempty element spans, attributes and parent edges checked against an independent
XML traversal. Zero-width elements remain in the converter JSON, without invented slots.
Schema validation not performed. See the collection report for raw static-validator findings.</p></details></main></html>"""


def navigation_page(rows: list[dict[str, Any]], revision: str) -> str:
    data = json.dumps(rows, ensure_ascii=False).replace("<", "\\u003c")
    passed = sum(r["status"] == "passed" for r in rows)
    return f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Les Fleurs du mal · Collection comparison</title><style>{STYLE}
header {{padding:16px 24px}} h1 {{font-size:26px;margin:8px 0}}
.controls {{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:12px 0}}
button,input,select {{font:14px system-ui;padding:8px;border:1px solid #49515e;border-radius:5px;background:#252a33;color:#dedfe3}}
select {{max-width:55vw;flex:1}} button {{cursor:pointer}} button:disabled {{opacity:.4}}
.comparison {{height:calc(100vh - 235px)}} #detail {{font-size:13px;min-height:20px}}
</style><header><div class="eyebrow">Charles Baudelaire · Collection QA</div>
<h1>Les Fleurs du mal</h1><div>{passed} / {len(rows)} documents verified · {len(rows) - passed} failed ·
revision {html.escape(revision[:12])}</div>
<div class="controls"><button id="previous">← Previous</button>
<select id="document" aria-label="Choose document"></select><button id="next">Next →</button>
<input id="search" type="search" placeholder="Filter title or filename" aria-label="Filter documents">
<span id="position"></span></div><div id="detail"></div>
<nav><a id="tei-link" target="_blank">Open TEI</a><a id="tf-link" target="_blank">Open TF</a>
<a id="corrected-link" target="_blank" hidden>Corrected XML</a>
<a id="xml-link" target="_blank">Original XML</a><a href="qa-report.json" target="_blank">Collection QA report</a>
<a href="validation.md" target="_blank">Raw validator report</a></nav></header>
<div class="workspace"><div class="comparison"><iframe id="tei" title="TEI source browser"></iframe>
<iframe id="tf" title="Text-Fabric browser"></iframe></div>{PANEL}</div>
<script>
const documents={data};
const select=document.getElementById('document'), search=document.getElementById('search');
let visible=documents, current=null;
{SCRIPT}
function show(id) {{
 const row=documents.find(d=>d.id===id); if(!row) return;
 current=row; showQuality(row); select.value=id; const index=visible.findIndex(d=>d.id===id);
 document.getElementById('position').textContent=`${{index+1}} / ${{visible.length}}`;
 document.getElementById('detail').textContent=row.name+' · '+(row.status==='passed'?
  (row.structural_repairs?.length?'Source repaired; structure verified':'Structure verified'):row.error)+
  (row.quality?' · Quality: '+row.quality.status:'');
 const corrected=document.getElementById('corrected-link');
 corrected.hidden=!row.comparison_source; if(row.comparison_source) corrected.href=row.comparison_source;
 for(const kind of ['tei','tf']) {{document.getElementById(kind).src=row[kind]; document.getElementById(kind+'-link').href=row[kind];}}
 document.getElementById('xml-link').href=row.source;
 document.getElementById('previous').disabled=index<=0;
 document.getElementById('next').disabled=index>=visible.length-1;
 history.replaceState(null,'','#'+encodeURIComponent(id));
}}
function filter() {{
 const query=search.value.toLocaleLowerCase();
 visible=documents.filter(d=>(d.title+' '+d.name).toLocaleLowerCase().includes(query));
 select.replaceChildren(...visible.map(d=>new Option((d.status==='passed'?'✓ ':'✗ ')+d.title+' — '+d.name,d.id)));
 if(visible.length) show(visible.some(d=>d.id===current?.id)?current.id:visible[0].id);
 else {{document.getElementById('position').textContent='0 matches'; document.getElementById('previous').disabled=true; document.getElementById('next').disabled=true;}}
}}
select.addEventListener('change',()=>show(select.value)); search.addEventListener('input',filter);
for(const [id,delta] of [['previous',-1],['next',1]]) document.getElementById(id).onclick=()=>{{
 const row=visible[visible.findIndex(d=>d.id===current?.id)+delta]; if(row) show(row.id);
}};
const initial=decodeURIComponent(location.hash.slice(1)); filter(); if(documents.some(d=>d.id===initial)) show(initial);
</script></html>"""


def run_collection(
    sources: list[Source],
    output: Path,
    validator: Path,
    repair_structural: bool = False,
    quality_report: Path | None = None,
) -> dict[str, Any]:
    require(not output.exists(), f"Output already exists: {output}")
    require(validator.is_file(), "Validator script not found")
    sources = sorted((s for s in sources if s.name.lower().endswith(".xml")), key=lambda s: s.name)
    require(bool(sources), "No XML files found")
    require(len({s.origin for s in sources}) == len(sources), "Duplicate source origins")
    originals = {s.origin: s.data for s in sources}
    repairs: dict[str, Any] = {}
    if quality_report:
        from .qa_quality import repaired_sources

        sources, repairs = repaired_sources(sources, quality_report)
    elif repair_structural:
        prepared = []
        for source in sources:
            candidate, diagnostics = structural_preview(source.data)
            if diagnostics and all(d["repairable"] for d in diagnostics):
                repairs[source.origin] = diagnostics
                source = Source(source.name, source.origin, candidate, source.revision)
            prepared.append(source)
        sources = prepared
    accepted: list[Source] = []
    expected: dict[str, dict[str, Any]] = {}
    rows = []
    for index, source in enumerate(sources):
        row: dict[str, Any] = {
            "id": f"doc-{index + 1:04d}",
            "name": source.name,
            "origin": source.origin,
            "sha256": hashlib.sha256(originals[source.origin]).hexdigest(),
            "comparison_sha256": hashlib.sha256(source.data).hexdigest(),
            "structural_repairs": repairs.get(source.origin, []),
            "title": Path(source.name).stem,
            "status": "failed",
        }
        try:
            view = oracle(source.data)
            docs, _ = parse(source, POLICY)
            require(len(docs) == 1 and bool(docs[0].text.strip()), "Expected one nonempty document")
            expected[docs[0].id] = view
            accepted.append(source)
            row.update(document_id=docs[0].id, title=view["title"], status="pending")
        except ConversionError as exc:
            row["error"] = str(exc)
        rows.append(row)
    require(bool(accepted), "No documents passed source preflight")
    manifest = convert([], output, sources=accepted, policy=POLICY)
    require(set(manifest["documents"]) == set(expected), "Converted document inventory differs")
    for source in accepted:
        row = next(r for r in rows if r["origin"] == source.origin)
        identity = row["document_id"]
        document = json.loads((output / "documents" / f"{identity}.json").read_text())
        source_tree = secure_tree(source.data)
        for field, path in {
            "titles": "titleStmt/t:title",
            "authors": "titleStmt/t:author",
            "publishers": "publicationStmt/t:publisher",
            "publication_dates": "publicationStmt/t:date",
        }.items():
            values = source_tree.xpath(
                f"/t:TEI/t:teiHeader/t:fileDesc/t:{path}", namespaces={"t": TEI}
            )
            assert isinstance(values, list), "Invalid metadata XPath result"
            want = [
                str(e.xpath("string(.)")).strip() for e in values if isinstance(e, etree._Element)
            ]
            require(document["metadata"][field] == want, f"Metadata differs: {field}")
        zeros = [
            {
                "path": e["key"],
                "tag": e["tag"],
                "namespace": e["namespace"],
                "attributes": e["attributes"],
                "parent": e["parent"],
                "start": e["start"],
                "end": e["end"],
            }
            for e in document["elements"]
            if e["start"] == e["end"]
        ]
        require(
            zeros == [e for e in expected[identity]["elements"] if e["start"] == e["end"]],
            "Zero-width annotation sidecar differs",
        )
    web = output / "browser"
    web.mkdir()
    write_json(web / "qa-report.json", {"status": "pending", "documents": rows})
    loader_receipts: dict[str, Any] = {}
    rendered: dict[str, dict[str, Any]] = {}
    with tempfile.TemporaryDirectory(prefix="collection-qa-") as temp:
        for name, factory in (("text-fabric", Fabric), ("context-fabric", ContextFabric)):
            root = Path(temp) / name
            shutil.copytree(output / "tf", root)
            for phase in ("cold", "warm"):
                api: Any = factory(locations=str(root), silent="deep").load(FEATURES, silent="deep")
                require(api is not False, f"{name} {phase} load failed")
                nodes = {api.F.document.v(n): n for n in api.F.otype.s("document")}
                require(
                    len(nodes) == len(api.F.otype.s("document")) and set(nodes) == set(expected),
                    "Loader document inventory differs",
                )
                proofs = {}
                covered = []
                element_count = 0
                for identity, view in expected.items():
                    actual, proof = verify_document(api, nodes[identity], view)
                    proofs[identity] = proof
                    covered.extend(api.E.oslots.s(nodes[identity]))
                    element_count += proof["elements"]
                    if name == "text-fabric" and phase == "warm":
                        rendered[identity] = actual
                require(
                    sorted(covered) == list(range(1, api.F.otype.maxSlot + 1)),
                    "Missing/overlapping document slots",
                )
                require(
                    element_count == len(api.F.otype.s("element")),
                    "Orphaned/overlapping element inventory",
                )
                loader_receipts[f"{name}-{phase}"] = proofs
    result = subprocess.run(
        [
            sys.executable,
            str(validator),
            str(output / "tf"),
            "--report",
            str(web / "validation.md"),
            "--json",
            str(web / "validation.json"),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    require(result.returncode in {0, 1}, f"Validator failed: {result.stderr}")
    raw = json.loads((web / "validation.json").read_text())
    errors = [i for i in raw["issues"] if i["severity"] == "error"]
    require(all(i["code"] == "TF064" for i in errors), "Unresolved static validation errors")
    for row, source in zip(rows, sources, strict=True):
        directory = web / row["id"]
        directory.mkdir()
        (directory / "source.xml").write_bytes(originals[source.origin])
        if source.origin in repairs:
            (directory / "corrected.xml").write_bytes(source.data)
            row["comparison_source"] = f"{row['id']}/corrected.xml"
        row.update(
            tei=f"{row['id']}/tei.html", tf=f"{row['id']}/tf.html", source=f"{row['id']}/source.xml"
        )
        if row["status"] == "pending":
            identity = row["document_id"]
            proof = loader_receipts["text-fabric-warm"][identity]
            row.update(status="passed", proof=proof)
            shutil.copyfile(output / "documents" / f"{identity}.json", directory / "document.json")
            (directory / "tei.html").write_text(
                reading_page(
                    expected[identity],
                    "TEI corrected source" if row["structural_repairs"] else "TEI source",
                    proof,
                )
            )
            (directory / "tf.html").write_text(
                reading_page(rendered[identity], "Text-Fabric output", proof)
            )
        else:
            message = f"<h1>Source rejected</h1><p>{html.escape(row['name'])}</p><pre>{html.escape(row['error'])}</pre>"
            shell = f'<!doctype html><meta charset="utf-8"><style>{STYLE}</style><main>{message}'
            (directory / "tei.html").write_text(
                shell
                + "<h2>Original source</h2><pre>"
                + html.escape(source.data.decode("utf-8", errors="replace"))
                + "</pre></main>"
            )
            (directory / "tf.html").write_text(
                shell
                + "<p>No TF document was created. Original bytes are retained; no automatic XML repair was applied.</p></main>"
            )
    revisions = sorted({s.revision for s in sources if s.revision})
    report = {
        "status": "partial" if len(accepted) != len(sources) else "passed",
        "source_revisions": revisions,
        "total": len(sources),
        "passed": len(accepted),
        "failed": len(sources) - len(accepted),
        "characters": manifest["graph"]["max_slot"],
        "documents": rows,
        "loaders": loader_receipts,
        "static_validator_raw_counts": raw["counts"],
        "static_validator_raw_exit": result.returncode,
        "static_validation": "passed-with-proven-whitespace-exception" if errors else "passed",
        "adjudication": {
            "TF064": "Every slot rendered exactly its source Unicode scalar, including whitespace.",
            "TF065": "Character slots must not insert separators.",
        },
        "reading_policy": {"choice": "original", "apparatus": "lemma", "notes": "separate"},
        "schema_validation": "not performed",
    }
    write_json(web / "qa-report.json", report)
    (web / "index.html").write_text(navigation_page(rows, ", ".join(revisions) or "local"))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument("--input", default=URL)
    parser.add_argument("--cached-inventory", type=Path)
    parser.add_argument("--quality-report", type=Path)
    args = parser.parse_args()
    if args.cached_inventory:
        inventory = json.loads(args.cached_inventory.read_text())
        sources = []
        for row in inventory:
            data = (args.cached_inventory.parent / row["file"]).read_bytes()
            require(hashlib.sha256(data).hexdigest() == row["sha256"], "Cached source hash differs")
            sources.append(Source(row["name"], row["origin"], data, row["revision"]))
    else:
        sources = acquire([args.input])
    result = run_collection(
        sources, args.output, args.validator, quality_report=args.quality_report
    )
    if args.quality_report:
        attach_quality(args.output / "browser", args.quality_report)
    print(json.dumps({k: result[k] for k in ("status", "total", "passed", "failed", "characters")}))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
