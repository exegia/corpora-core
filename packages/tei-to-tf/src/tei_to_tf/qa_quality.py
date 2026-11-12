"""Join audited quality receipts to the independently verified comparison browser."""

import hashlib
import html
import json
from pathlib import Path
from typing import Any

from .model import ConversionError
from .parse import secure_tree


def repaired_sources(sources: list[Any], report_path: Path) -> tuple[list[Any], dict[str, Any]]:
    """Bind prepared copies to originals before independent TEI/TF comparison."""
    from .model import Source

    report = json.loads(report_path.read_text())
    rows = [dict(origin=s.origin, sha256=hashlib.sha256(s.data).hexdigest()) for s in sources]
    join_quality(rows, report)
    root = report_path.parent.resolve()
    prepared, repairs = [], {}
    for source, row in zip(sources, rows, strict=True):
        receipt = row["quality"]
        if receipt.get("repaired_file"):
            path = (root / receipt["repaired_file"]).resolve()
            if not path.is_relative_to(root):
                raise ConversionError("Repaired source path escapes report directory")
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != receipt.get("repaired_sha256"):
                raise ConversionError("Repaired source hash differs from quality receipt")
            if data != source.data:
                repairs[source.origin] = receipt["pass_2"]
                source = Source(source.name, source.origin, data, source.revision)
        prepared.append(source)
    return prepared, repairs


def reading_issues(
    data: bytes, view: dict[str, Any], diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map original XML field offsets to verified TF ranges, never by word search."""
    tree = secure_tree(data)
    nodes = {tree.getpath(n): n for n in tree.iter() if isinstance(n.tag, str)}
    elements = {e["path"]: e for e in view["elements"]}
    result = []
    for issue in diagnostics:
        path, field = issue.get("path"), issue.get("field")
        if issue.get("role") != "corpus" or field not in {"text", "tail"}:
            continue
        if path not in nodes or path not in elements:
            continue
        value = getattr(nodes[path], field) or ""
        start, end = issue["start"], issue["end"]
        base = elements[path]["start" if field == "text" else "end"]
        if not (0 <= start < end <= len(value)):
            continue
        if value[start:end] != issue["text"]:
            continue
        if view["text"][base : base + len(value)] != value:
            continue
        result.append(dict(issue, start=base + start, end=base + end))
    return result


def marked_text(text: str, start: int, end: int, issues: list[dict[str, Any]]) -> str:
    boundaries = {start, end}
    relevant = [d for d in issues if d["start"] < end and d["end"] > start]
    for issue in relevant:
        boundaries.update((max(start, issue["start"]), min(end, issue["end"])))
    positions = sorted(boundaries)
    parts = []
    for a, b in zip(positions, positions[1:], strict=False):
        value = html.escape(text[a:b])
        active = [d for d in relevant if d["start"] <= a and d["end"] >= b]
        if active:
            score = max(d["score"] for d in active)
            tips = []
            for d in active:
                suggestions = (
                    ", ".join(d.get("suggestions", [])) or "No suggestion; review optional"
                )
                if d.get("blocking") and not d.get("suggestions"):
                    suggestions = "No safe automatic suggestion; manual review"
                ai_tip = (
                    f"AI: {d['ai_suggestion']}"
                    if d.get("ai_suggestion")
                    else f"AI: {d.get('ai_status', 'not requested')}"
                )
                tips.append(
                    f"Score {d['score']} · {d.get('reason', '')} · {ai_tip} "
                    f"· Dictionary: {suggestions}"
                )
            tip = html.escape("\n".join(tips), quote=True)
            color = "red" if score >= 90 else "orange" if score >= 60 else "yellow"
            value = (
                f'<span class="qa-word qa-{color}" tabindex="0" '
                f'data-tip="{tip}" aria-label="{html.escape(text[a:b], quote=True)}: {tip}">'
                f"{value}</span>"
            )
        parts.append(value)
    return "".join(parts)


MARK_STYLE = """
.qa-word {--score-color:#fb923c;--tooltip-text:#24170d;
 text-decoration:underline wavy var(--score-color);
 text-underline-offset:4px;
 text-decoration-thickness:2px;position:relative;cursor:help}
.qa-red {--score-color:#f87171;--tooltip-text:#291011}
.qa-yellow {--score-color:#eab308;--tooltip-text:#292000}
.qa-word:hover::after,.qa-word:focus::after {content:attr(data-tip);position:absolute;
 z-index:10;left:0;top:100%;width:280px;max-width:70vw;white-space:normal;
 background:var(--score-color);color:var(--tooltip-text,white);padding:10px;border-radius:6px;
 font:13px/1.5 system-ui;
 text-decoration:none;box-shadow:0 3px 12px #0004}
"""


def join_quality(rows: list[dict[str, Any]], report: dict[str, Any]) -> None:
    documents = report["documents"]
    by_source = {r["source"]: r for r in documents}
    if len(by_source) != len(documents) or set(by_source) != {r["origin"] for r in rows}:
        raise ConversionError("Quality report source inventory differs from comparison")
    for row in rows:
        receipt = by_source[row["origin"]]
        if receipt["source_sha256"] != row["sha256"]:
            raise ConversionError("Quality report source hash differs from comparison")
    for row in rows:
        row["quality"] = by_source[row["origin"]]


def attach_quality(browser: Path, report_path: Path) -> None:
    from tf.fabric import Fabric

    from .qa_collection import FEATURES, navigation_page, oracle, reading_page, verify_document

    report = json.loads((browser / "qa-report.json").read_text())
    quality = json.loads(report_path.read_text())
    join_quality(report["documents"], quality)
    api = Fabric(locations=str(browser.parent / "tf"), silent="deep").load(FEATURES, silent="deep")
    if api is False:
        raise ConversionError("TF load failed while adding diagnostics")
    nodes = {api.F.document.v(n): n for n in api.F.otype.s("document")}
    for row in report["documents"]:
        if row["status"] != "passed":
            continue
        data = (browser / row.get("comparison_source", row["source"])).read_bytes()
        view, proof = verify_document(api, nodes[row["document_id"]], oracle(data))
        receipt = row["quality"]
        final_basis = hashlib.sha256(data).hexdigest() == receipt.get("repaired_sha256")
        issues = reading_issues(data, view, receipt["pass_3" if final_basis else "pass_1"])
        label = (
            "Text-Fabric corrected preview"
            if row.get("structural_repairs")
            else "Text-Fabric output"
        )
        page = reading_page(view, label, proof, issues)
        (browser / row["tf"]).write_text(page)
        row["tf"] += "?v=" + hashlib.sha256(page.encode()).hexdigest()[:12]
    (browser / "quality-report.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2))
    (browser / "index.html").write_text(
        navigation_page(report["documents"], ", ".join(report["source_revisions"]))
    )


PANEL = """
<style>
.workspace {display:flex;height:calc(100vh - 235px);min-height:350px}
.workspace .comparison {flex:1;min-width:0;height:100%}
#quality {flex:0 0 46px;background:#1d2026;border-left:1px solid #353a43;overflow:auto}
#quality[hidden] {display:none}
#quality[open] {flex-basis:min(440px,45vw)}
#quality > summary {padding:16px 12px;font:600 14px system-ui;color:#91bde3;
 cursor:pointer;writing-mode:vertical-rl;list-style-position:inside}
#quality[open] > summary {writing-mode:horizontal-tb;border-bottom:1px solid #353a43}
.quality-content {padding:16px}
#quality h2 {font:600 18px system-ui;margin:0 0 8px}
#quality-summary {margin:8px 0;font:14px system-ui}
.issues-scroll {background:#22262e}
#issues {border-collapse:collapse;width:100%;font:13px/1.5 system-ui}
#issues thead {display:none}
#issues tr {display:block;padding:10px 12px;border-bottom:1px solid #353a43}
#issues td {display:block;padding:3px 0;overflow-wrap:anywhere}
#issues td:nth-child(3)::before {content:'Role: ';font-weight:600}
#issues td:nth-child(4)::before {content:'Suggestions / repair: ';font-weight:600}
#issues td:nth-child(5) {font-size:12px;color:#aeb8c5}
.blocking {color:#ff8c8c;font-weight:600}.warning {color:#edc56c}
</style>
<details id="quality" hidden aria-label="Quality diagnostics">
<summary>Diagnostics</summary><div class="quality-content">
<h2>Language, spelling &amp; XML diagnostics</h2>
<p>TEI and TF panes include successful XML repairs. Original XML remains available.
Quality blockers remain
visible here; a structurally verified TF preview is not a quality-approved export.</p>
<div class="controls"><label>Pass <select id="quality-pass">
<option value="pass_3">3 · Remaining issues</option>
<option value="pass_1">1 · Initial findings</option>
<option value="pass_2">2 · Applied repairs</option></select></label>
<label><input type="checkbox" id="blocking-only"> Blocking only</label>
<a href="quality-report.json" target="_blank">Full quality report</a></div>
<div id="quality-summary" role="status"></div>
<div class="issues-scroll"><table id="issues"><thead><tr>
<th>Outcome / score</th><th>Text / issue</th><th>Role</th><th>Suggestions / repair</th>
<th>Reason / source location</th></tr></thead><tbody></tbody></table></div></div></details>
"""

SCRIPT = """
function showQuality(row) {
 const q=row.quality, panel=document.getElementById('quality');
 panel.hidden=!q; document.body.classList.toggle('quality-enabled',Boolean(q));
 if(!q) return;
 const pass=document.getElementById('quality-pass').value;
 const all=q[pass]||[], blocking=document.getElementById('blocking-only').checked;
 const issues=all.filter(d=>!blocking||d.blocking);
 const language=q.language;
 document.getElementById('quality-summary').textContent=
  'Quality: '+q.status+' · '+
  (language?language.locale+' / '+language.dictionary:'Language unavailable')+
  ' · '+issues.length+' of '+all.length+' findings shown · '+
  all.filter(d=>d.blocking).length+' blocking · '+(q.pass_2||[]).length+' applied repairs';
 const body=document.querySelector('#issues tbody'); body.replaceChildren();
 for(const d of issues) {
  const tr=document.createElement('tr');
  const applied=pass==='pass_2';
  const outcome=applied?(d.validated===false?'Proposed; not validated':'Repaired'):
   d.blocking?'Blocked':'Warning · passes';
  const suggestion=applied?String(d.before)+' → '+String(d.after):
   d.ai_suggestion?'AI: '+d.ai_suggestion+' · '+(d.ai_reason||''):
   d.replacement?'Proposed: '+d.replacement:
   d.after?'Proposed: '+d.after:
   d.suggestions?.length?d.suggestions.join(', '):'No safe automatic suggestion; manual review';
  const values=[outcome+' · '+(d.score??'N/A (structural)'),d.text||d.code||d.before||'Repair',
   d.role||'XML / structure',suggestion,
   [d.reason||d.message,d.ai_status?'AI: '+d.ai_status:null,d.path,d.field,
    d.line?'line '+d.line:null,
    d.start!==undefined?'offset '+d.start:null].filter(Boolean).join(' · ')];
  values.forEach((value,i)=>{const td=document.createElement('td');td.textContent=value;
   if(i===0) td.className=d.blocking&&!applied?'blocking':'warning';tr.append(td);});
  body.append(tr);
 }
 if(!issues.length) {const tr=document.createElement('tr'),td=document.createElement('td');
  td.colSpan=5;td.textContent='No findings in this pass/filter.';tr.append(td);body.append(tr);}
}
for(const id of ['quality-pass','blocking-only'])
 document.getElementById(id).addEventListener('change',()=>{if(current) showQuality(current);});
"""
