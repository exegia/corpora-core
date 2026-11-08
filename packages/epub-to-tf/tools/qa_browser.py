"""Build a local dark-mode comparison page from an exported EPUB bundle."""

# ruff: noqa: E501 -- Inline CSS and JavaScript are a self-contained QA artifact.

import argparse
import json
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET
from zipfile import ZipFile

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
    with ZipFile(bundle / "sources/original.epub") as archive:
        for member in archive.namelist():
            if member.endswith("/"):
                continue
            if not _safe_member(member):
                raise ValueError(f"Unsafe archive member: {member}")
            target = output / "source" / member
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(member))
        for index, item_id in enumerate(manifest["documents"], 1):
            document = json.loads(
                (bundle / "documents" / f"{index:04}.json").read_text(encoding="utf-8")
            )
            body = ET.fromstring(archive.read(document["member"])).find(f"{{{XHTML}}}body")
            if body is None:
                raise ValueError(f"Missing body in {document['member']}")
            docs.append(
                {
                    "id": item_id,
                    "member": document["member"],
                    "source": _reading_text(body),
                    "tf": (bundle / "documents" / f"{index:04}.txt").read_text(encoding="utf-8"),
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
:root{color-scheme:dark}*{box-sizing:border-box}body{font:15px system-ui;margin:0;color:#e7edf6;background:#10151f}header{padding:22px 28px;background:#080d16}h1{margin:0 0 8px;font-size:23px}p{margin:0 0 10px}main{padding:18px 28px}select{font:inherit;padding:7px;margin-right:12px;background:#1f2937;color:#f3f6fa;border:1px solid #607086;border-radius:6px}.status{font-weight:700;color:#68d99b}.bad{color:#ff8080}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.panel{background:#192231;border:1px solid #344157;border-radius:8px;overflow:hidden}.panel h2{font-size:17px;margin:0;padding:12px 16px;background:#263348}.text{white-space:pre-wrap;overflow:auto;max-height:480px;padding:16px;font:14px/1.55 Georgia,serif}.source-view{width:100%;height:480px;border:0;background:#fff}.assets{display:flex;gap:12px;flex-wrap:wrap;padding:16px}.assets img,.assets video{max-width:160px;max-height:160px;object-fit:contain;background:#fff;border:1px solid #526173}.assets audio{max-width:180px}.asset{max-width:190px;overflow-wrap:anywhere;font-size:12px;color:#c7d4e6}.asset a{color:#9cc9ff}.meta{margin-top:15px;color:#aab8cb}footer{padding:20px 28px;font-size:13px;color:#aab8cb}
</style>
<header><h1>EPUB ↔ Text-Fabric</h1><p id="summary"></p><p>Original XHTML keeps its EPUB styling. The converted text and asset inventory use dark mode.</p></header>
<main><label>Spine document <select id="chapter"></select></label><span id="status" class="status"></span><div id="meta" class="meta"></div>
<div class="grid"><section class="panel"><h2>Original EPUB XHTML</h2><iframe id="source" class="source-view" sandbox=""></iframe></section><section class="panel"><h2>Text-Fabric document text</h2><div id="tf" class="text"></div></section></div>
<div class="grid"><section class="panel"><h2>Source asset references</h2><div id="original-assets" class="assets"></div></section><section class="panel"><h2>Copied TF assets</h2><div id="exported-assets" class="assets"></div></section></div></main>
<footer>Text status compares an independent parse of each original XHTML body with the exported document text. Note bodies and inline XML assets follow the converter's separate scope policy.</footer>
<script>
const docs=__DOCS__, select=document.querySelector('#chapter');
const count=docs.reduce((n,d)=>n+[...d.source].length,0), assets=docs.reduce((n,d)=>n+d.assets.length,0);
document.querySelector('#summary').textContent=docs.length+' spine documents · '+count.toLocaleString()+' Unicode characters · '+assets+' asset references';
docs.forEach((d,i)=>{let option=document.createElement('option');option.value=i;option.textContent=(i+1)+'. '+d.member;select.append(option)});
function card(asset, source){let box=document.createElement('div');box.className='asset';let path=source&&asset.source_end===null?'source/'+asset.target_member:asset.file;
let media;if(asset.media_type.startsWith('image/')){media=document.createElement('img');media.src=path;media.alt=asset.alt||asset.kind}
else if(asset.media_type.startsWith('audio/')){media=document.createElement('audio');media.src=path;media.controls=true}
else if(asset.media_type.startsWith('video/')){media=document.createElement('video');media.src=path;media.controls=true}
else{media=document.createElement('a');media.href=path;media.textContent=asset.media_type}
let caption=document.createElement('div');caption.textContent=asset.kind+' · '+asset.scope+' @ '+asset.text_offset+' · '+asset.href;box.append(media,caption);return box}
function show(){let d=docs[Number(select.value)],equal=d.source===d.tf;document.querySelector('#source').src='source/'+d.member;document.querySelector('#tf').textContent=d.tf;
let status=document.querySelector('#status');status.textContent=equal?'✓ Exact text match':'✗ Text mismatch';status.classList.toggle('bad',!equal);
document.querySelector('#meta').textContent=[...d.source].length.toLocaleString()+' characters · '+d.headings+' heading nodes · '+d.assets.length+' asset references';
for(let [selector,source] of [['#original-assets',true],['#exported-assets',false]]){let box=document.querySelector(selector);box.replaceChildren(...d.assets.map(a=>card(a,source)))}}
select.addEventListener('change',show);show();
</script></html>"""
    path = output / "index.html"
    path.write_text(
        page.replace("__DOCS__", json.dumps(docs, ensure_ascii=False).replace("</", "<\\/")),
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
