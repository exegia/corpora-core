"""Build a local dark-mode comparison page from an exported EPUB bundle."""

# ruff: noqa: E501 -- Inline CSS and JavaScript are a self-contained QA artifact.

import argparse
import json
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from epub_to_tf.reading import normalize_slots

XHTML = "http://www.w3.org/1999/xhtml"
EPUB_TYPE = "{http://www.idpf.org/2007/ops}type"


def _reading_text(node: ET.Element) -> str:
    """Independently project body text, excluding separately modeled notes/assets."""
    parts = [node.text or ""]
    for child in node:
        kind = (child.attrib.get(EPUB_TYPE, "") + " " + child.attrib.get("role", "")).split()
        local = child.tag.rsplit("}", 1)[-1]
        if not (
            set(kind) & {"footnote", "endnote", "doc-footnote", "doc-endnote"}
        ) and local not in {"svg", "math"}:
            parts.append(_reading_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return (
        not path.is_absolute()
        and not any(part in {"", ".", ".."} for part in name.split("/"))
        and "\\" not in name
        and ":" not in name
    )


def build(bundle: Path, output: Path) -> Path:
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    output.mkdir(parents=True, exist_ok=True)
    docs = []
    repaired = manifest["validated_source"]["file"] != manifest["source"]["file"]
    with (
        ZipFile(bundle / "sources/original.epub") as archive,
        ZipFile(bundle / manifest["validated_source"]["file"]) as reading_archive,
    ):
        for member in archive.namelist():
            if member.endswith("/"):
                continue
            if not _safe_member(member):
                raise ValueError(f"Unsafe archive member: {member}")
            target = output / "source" / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
        if repaired:
            for member in reading_archive.namelist():
                if member.endswith("/"):
                    continue
                if not _safe_member(member):
                    raise ValueError(f"Unsafe repaired archive member: {member}")
                target = output / "validated" / member
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(reading_archive.read(member))
        for index, item_id in enumerate(manifest["documents"], 1):
            document = json.loads(
                (bundle / "documents" / f"{index:04}.json").read_text(encoding="utf-8")
            )
            body = ET.fromstring(reading_archive.read(document["member"])).find(f"{{{XHTML}}}body")
            if body is None:
                raise ValueError(f"Missing body in {document['member']}")
            source_text = _reading_text(body)
            expected_reading = "".join(normalize_slots(source_text, document["elements"])[0])
            docs.append(
                {
                    "id": item_id,
                    "member": document["member"],
                    "view": "validated" if repaired else "source",
                    "source_chars": len(source_text),
                    "source_matches": source_text == document["text"],
                    "reading_matches": expected_reading == document["reading_text"],
                    "tf": (bundle / "documents" / f"{index:04}.reading.txt").read_text(
                        encoding="utf-8"
                    ),
                    "semantics": [
                        element["semantic_kind"]
                        for element in document["elements"]
                        if "semantic_kind" in element
                    ],
                    "assets": [
                        asset for asset in manifest["assets"] if asset["document_id"] == item_id
                    ],
                    "headings": sum(
                        element["tag"] in {"h1", "h2", "h3"} for element in document["elements"]
                    ),
                }
            )
    for asset in manifest["assets"]:
        if not _safe_member(asset["file"]):
            raise ValueError(f"Unsafe asset path: {asset['file']}")
        target = output / asset["file"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((bundle / asset["file"]).read_bytes())
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><title>EPUB ↔ Text-Fabric QA</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{font:15px system-ui;margin:0;color:#e7edf6;background:#10151f}header{padding:22px 28px;background:#080d16}h1{margin:0 0 8px;font-size:23px}p{margin:0 0 10px}main{padding:18px 28px}select,button{font:inherit;padding:7px;margin-right:12px;background:#1f2937;color:#f3f6fa;border:1px solid #607086;border-radius:6px;cursor:pointer}.status{font-weight:700;color:#68d99b}.bad{color:#ff8080}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.panel{background:#192231;border:1px solid #344157;border-radius:8px;overflow:hidden}.panel h2{font-size:17px;margin:0;padding:12px 16px;background:#263348}.text{white-space:pre-wrap;overflow:auto;max-height:480px;padding:16px;font:14px/1.55 Georgia,serif}.source-view{width:100%;height:480px;border:0;background:#fff}.assets{display:flex;gap:12px;flex-wrap:wrap;padding:16px}.assets img,.assets video{max-width:160px;max-height:160px;object-fit:contain;background:#fff;border:1px solid #526173}.assets audio{max-width:180px}.asset{max-width:190px;overflow-wrap:anywhere;font-size:12px;color:#c7d4e6}.asset a{color:#9cc9ff}.meta{margin-top:15px;color:#aab8cb}footer{padding:20px 28px;font-size:13px;color:#aab8cb}
</style>
<header><h1>EPUB ↔ Text-Fabric</h1><p id="summary"></p><p>The validated XHTML keeps its EPUB styling. The converted text and asset inventory use dark mode.</p></header>
<main><label>Spine document <select id="chapter"></select></label><span id="status" class="status"></span><div id="meta" class="meta"></div><details><summary>Publication table of contents</summary><ol id="toc-entries"></ol></details>
<div class="grid"><section class="panel"><h2>EPUB XHTML used for validation</h2><iframe id="source" class="source-view" sandbox=""></iframe><p><button id="source-toggle" type="button">Show original XHTML</button></p></section><section class="panel"><h2>Text-Fabric reading text</h2><div id="tf" class="text"></div></section></div>
<div class="panel"><h2>Semantic markers</h2><div id="semantics" class="meta"></div></div>
<div class="grid"><section class="panel"><h2>Source asset references</h2><div id="original-assets" class="assets"></div></section><section class="panel"><h2>Copied TF assets</h2><div id="exported-assets" class="assets"></div></section></div></main>
<footer>Source slots retain every original character. The default TF reading view collapses layout whitespace while preserving a source-text format and source offsets. Status checks the independently parsed XHTML source and the derived reading view. Use the button above to view the untouched archive member.</footer>
<script>
const docs=__DOCS__, toc=__TOC__, select=document.querySelector('#chapter');
const count=docs.reduce((n,d)=>n+[...d.tf].length,0), assets=docs.reduce((n,d)=>n+d.assets.length,0);
document.querySelector('#summary').textContent=docs.length+' spine documents · '+count.toLocaleString()+' reading characters · '+assets+' asset references · '+toc.length+' TOC entries';
docs.forEach((d,i)=>{let option=document.createElement('option');option.value=i;option.textContent=(i+1)+'. '+d.member;select.append(option)});
const byMember=new Map(docs.map((d,i)=>[d.member,i]));for(const entry of toc){let li=document.createElement('li'),button=document.createElement('button');li.style.marginLeft=(entry.level-1)*18+'px';button.textContent=entry.label||entry.target_member;button.disabled=!byMember.has(entry.target_member);button.addEventListener('click',()=>{select.value=byMember.get(entry.target_member);show()});li.append(button);document.querySelector('#toc-entries').append(li)}
function card(asset, source){let box=document.createElement('div');box.className='asset';let path=source&&asset.source_end===null?'source/'+asset.target_member:asset.file;
let media;if(asset.media_type.startsWith('image/')){media=document.createElement('img');media.src=path;media.alt=asset.alt||asset.kind}
else if(asset.media_type.startsWith('audio/')){media=document.createElement('audio');media.src=path;media.controls=true}
else if(asset.media_type.startsWith('video/')){media=document.createElement('video');media.src=path;media.controls=true}
else{media=document.createElement('a');media.href=path;media.textContent=asset.media_type}
let caption=document.createElement('div');caption.textContent=asset.kind+' · '+asset.scope+' @ '+asset.text_offset+' · '+asset.href;box.append(media,caption);return box}
function show(){let d=docs[Number(select.value)],equal=d.source_matches&&d.reading_matches;document.querySelector('#source').src=d.view+'/'+d.member;document.querySelector('#source-toggle').hidden=d.view==='source';document.querySelector('#source-toggle').textContent='Show original XHTML';document.querySelector('#tf').textContent=d.tf;
let status=document.querySelector('#status');status.textContent=equal?'✓ Source and reading match':'✗ Text mismatch';status.classList.toggle('bad',!equal);
document.querySelector('#meta').textContent=d.source_chars.toLocaleString()+' source characters · '+[...d.tf].length.toLocaleString()+' reading characters · '+d.assets.length+' asset references';
let kinds={};for(const kind of d.semantics)kinds[kind]=(kinds[kind]||0)+1;document.querySelector('#semantics').textContent=Object.entries(kinds).map(([k,n])=>k+': '+n.toLocaleString()).join(' · ');
for(let [selector,source] of [['#original-assets',true],['#exported-assets',false]]){let box=document.querySelector(selector);box.replaceChildren(...d.assets.map(a=>card(a,source)))}}
select.addEventListener('change',show);show();
document.querySelector('#source-toggle').addEventListener('click',()=>{let d=docs[Number(select.value)],button=document.querySelector('#source-toggle'),original=button.textContent==='Show original XHTML';document.querySelector('#source').src=(original?'source':d.view)+'/'+d.member;button.textContent=original?'Show validated XHTML':'Show original XHTML'});
</script></html>"""
    path = output / "index.html"
    path.write_text(
        page.replace(
            "__DOCS__", json.dumps(docs, ensure_ascii=False).replace("</", "<\\/")
        ).replace("__TOC__", json.dumps(manifest["toc"], ensure_ascii=False).replace("</", "<\\/")),
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(build(args.bundle, args.output))


if __name__ == "__main__":
    main()
