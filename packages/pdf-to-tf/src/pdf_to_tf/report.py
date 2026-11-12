"""Write conversion-report.json and a readable conversion-report.md."""

import json
from pathlib import Path
from typing import Any

MAX_ROWS_PER_CODE = 50

MAPPING = [
    ("Page", "`pb@n` + `facsimile/surface`", "`page` node: `page`, `facs_surface`, `facs_*`"),
    ("Line bounds / word bounds", "`zone` via `@facs`", "`facs_ulx/uly/lrx/lry` (int, 1/10 unit)"),
    ("Heading h1–h4", "`div[@type=section]/head[@type=hN]`", "`element` `head`, parent edges"),
    ("Paragraph line", "`p[@n]/seg[@type=line]`", "`element` `tei_tag=seg` (and `p`)"),
    ("List item", "`list/item`", "`element` `tei_tag=item`"),
    ("Reference", "`listBibl/bibl`", "`element` `tei_tag=bibl`"),
    ("Citation", "`ab[@type=citation]`", "`element` `tei_tag=ab`"),
    ("Footnote line", "`note[@place=foot]/seg`", "`element` `tei_tag=seg` (and `note`)"),
    ("Running header / footer", "`fw[@type=header|footer]`", "`element` `tei_tag=fw`"),
    ("Front matter, abstract, keywords", "`ab[@type]/seg`", "`element` `tei_tag=seg` (and `ab`)"),
    ("Table cell", "`table/row/cell`", "`element` `tei_tag=cell`"),
    ("OCR word + confidence", "`w[@cert]`", "`element` `tei_tag=w`, `attr_cert_*`"),
    ("Bold / italic / link", "`hi[@rend]` / `ref[@target]`", "`element` `tei_tag=hi|ref`"),
    ("Line identity", "`@xml:id` p{page}e{index}", "`attr_id_*` feature"),
    ("Page language (reliable)", "`@xml:lang`", "`attr_lang_*` feature"),
    ("Image / graph candidate", "`figure` (no text)", "not a node; TEI + document JSON"),
]  # fmt: skip


def location(issue: dict[str, Any]) -> str:
    parts = []
    if issue.get("page") is not None:
        parts.append(f"p.{issue['page']}")
    if issue.get("element_index") is not None:
        parts.append(f"line {issue['element_index']}")
    if issue.get("word_index") is not None:
        parts.append(f"word {issue['word_index']}")
    bounds = issue.get("bounds")
    if bounds:
        parts.append("@({x:.0f},{y:.0f} {width:.0f}×{height:.0f})".format(**bounds))
    if issue.get("xml_id"):
        parts.append(f"`{issue['xml_id']}`")
    if issue.get("tf_node") is not None:
        parts.append(f"TF {issue['tf_node']}")
    return " · ".join(parts) or "document"


def cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def markdown(report: dict[str, Any]) -> str:
    gate = report["gate"]
    title = report.get("title") or Path(report["source"]["path"]).name
    lines = [
        f"# PDF → TEI → TF conversion report: {title}",
        "",
        f"**Status: {report['status']}**",
        "",
        f"- Score: **{gate['score']:.2%}** (gate: score > {gate['min_score']:.0%}; "
        f"{'passed' if gate['passed'] else 'not passed'})",
        f"- Source: `{report['source']['path']}` (sha256 `{report['source']['sha256']}`)",
        f"- Pages: {report['pages']}",
        "- Issues: "
        + (", ".join(f"{n} {k}" for k, n in sorted(report["issue_counts"].items())) or "none"),
        "",
        "The score is the character-weighted mean of corpora-pdf page evidence "
        "(OCR word confidence, or text-layer agreement with OCR of the rendered page). "
        "It is not accuracy against a reference transcription.",
        "",
    ]
    if report["status"] == "gated":
        lines += [
            "No TEI or TF was written because the score did not pass the gate. "
            "Fix the causes below and run again.",
            "",
            *(f"- {note}" for note in gate.get("diagnosis", [])[:20]),
            "",
        ]
    lines += [
        "## Pages",
        "",
        "| Page | Method | Characters | Score | Basis |",
        "| ---: | --- | ---: | ---: | --- |",
    ]
    for page in gate["pages"]:
        score = "—" if page["score"] is None else f"{page['score']:.2%}"
        lines.append(
            f"| {page['page']} | {page['method']} | {page['characters']} | {score} | "
            f"{page['basis'] or '—'} |"
        )
    lines += ["", "## Issues", ""]
    if not report["issues"]:
        lines += ["No issues found.", ""]
    by_code: dict[str, list[dict[str, Any]]] = {}
    for issue in report["issues"]:
        by_code.setdefault(issue["code"], []).append(issue)
    for code, items in by_code.items():
        first = items[0]
        lines += [
            f"### {first['severity']}: `{code}` ({len(items)})",
            "",
            f"Suggested fix: {first['suggestion']}",
            "",
            "| Where | Detail | Text |",
            "| --- | --- | --- |",
        ]
        for issue in items[:MAX_ROWS_PER_CODE]:
            where, detail, text = location(issue), issue["message"], issue.get("text")
            lines.append(f"| {cell(where)} | {cell(detail)} | {cell(text)} |")
        if len(items) > MAX_ROWS_PER_CODE:
            lines.append(
                f"| … | {len(items) - MAX_ROWS_PER_CODE} more in conversion-report.json | |"
            )
        lines.append("")
    if "verification" in report:
        checked = report["verification"]["checked"]
        lines += [
            "## Verification",
            "",
            f"Real Text-Fabric load passed. Checked {checked['lines']} lines, "
            f"{checked['words']} OCR words and {checked['pages']} pages against the "
            f"extraction: text, TEI tag, zone coordinates, page membership and word "
            f"confidence. Mismatches: {report['verification']['mismatches']}.",
            "",
            "## Feature mapping",
            "",
            "| PDF extraction | TEI | Text-Fabric |",
            "| --- | --- | --- |",
            *(f"| {a} | {b} | {c} |" for a, b, c in MAPPING),
            "",
            "Characters added: newline between lines and blocks, tab between table cells. "
            "Headings, lists, tables and paragraph grouping are layout heuristics.",
            "",
        ]
    lines += ["## Outputs", ""]
    for name, path in report["outputs"].items():
        lines.append(f"- {name}: `{path}`" if path else f"- {name}: not written")
    lines += [
        "- extraction: `extraction.json`",
        f"- original PDF: `sources/{report['source']['sha256']}`",
        "- hashes: `checksums.json`",
        "",
    ]
    return "\n".join(lines)


def write_reports(stage: Path, report: dict[str, Any]) -> None:
    (stage / "conversion-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    (stage / "conversion-report.md").write_text(markdown(report), encoding="utf-8")
