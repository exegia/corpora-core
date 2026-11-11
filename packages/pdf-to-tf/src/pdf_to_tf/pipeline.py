"""PDF → (score gate) → TEI → Text-Fabric, with a located issue report."""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from tei_to_tf import Policy
from tei_to_tf import convert as tei_convert
from tei_to_tf.model import Source

from .gate import DEFAULT_MIN_SCORE, diagnose, evaluate
from .issues import Issue, extraction_issues
from .report import write_reports
from .tei import build_tei
from .verify import verify

FORMAT = "corpora-pdf-to-tf/1"
SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


class ConversionFailed(RuntimeError):
    """The PDF could not be extracted or the input is unusable."""


Runner = Callable[[list[str]], subprocess.CompletedProcess[bytes]]


def run(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(command, capture_output=True, check=False)


def extract(
    pdf: Path,
    extractor: str,
    languages: str,
    tessdata: Path | None,
    max_pages: int | None,
    visual_check: bool,
    runner: Runner = run,
) -> tuple[dict[str, Any], list[str]]:
    command = [extractor, str(pdf), "--languages", languages]
    if tessdata:
        command += ["--tessdata", str(tessdata)]
    if max_pages:
        command += ["--max-pages", str(max_pages)]
    if not visual_check:
        command.append("--no-visual-check")
    try:
        result = runner(command)
    except OSError as exc:
        raise ConversionFailed(f"cannot run extractor {extractor}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise ConversionFailed(f"extraction failed: {detail}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ConversionFailed(f"extractor returned invalid JSON: {exc}") from exc
    if not isinstance(value, dict) or not isinstance(value.get("pages"), list):
        raise ConversionFailed("extractor JSON has no pages")
    return value, command


def first_line(runner: Runner, command: list[str]) -> str:
    try:
        result = runner(command)
    except OSError:
        return ""
    text = (result.stdout or b"") + (result.stderr or b"")
    lines = text.decode("utf-8", "replace").strip().splitlines()
    return lines[0].strip() if lines else ""


def pdf_title(pdf: Path, runner: Runner) -> str:
    try:
        result = runner(["pdfinfo", str(pdf)])
    except OSError:
        return pdf.stem
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("Title:") and line[6:].strip():
            return line[6:].strip()
    return pdf.stem


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def convert(
    pdf: Path,
    output: Path,
    *,
    extractor: str = "corpora-pdf-extract",
    languages: str = "eng",
    tessdata: Path | None = None,
    max_pages: int | None = None,
    visual_check: bool = True,
    min_score: float = DEFAULT_MIN_SCORE,
    schema: Path | None = None,
    extraction: dict[str, Any] | None = None,
    runner: Runner = run,
) -> dict[str, Any]:
    """Write a new bundle at ``output`` and return its report.

    ``report["status"]`` is ``converted``, ``converted_with_issues``, ``gated`` (score at
    or below ``min_score``; no TEI/TF written) or ``verification_failed``. Pass a
    precomputed ``extraction`` to skip running the extractor.
    """
    pdf = pdf.absolute()
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ConversionFailed(f"output already exists: {output}")
    data = pdf.read_bytes()
    source_sha = hashlib.sha256(data).hexdigest()
    command: list[str] = []
    if extraction is None:
        extraction, command = extract(
            pdf, extractor, languages, tessdata, max_pages, visual_check, runner
        )
    if extraction.get("source_sha256") != source_sha:
        raise ConversionFailed("extraction does not belong to this PDF (sha256 differs)")
    gate = evaluate(extraction, min_score)
    tools = {
        "corpora-pdf-extract": "path " + extractor,
        "pdftohtml": first_line(runner, ["pdftohtml", "-v"]),
        "tesseract": first_line(runner, ["tesseract", "--version"]),
    }
    issues = extraction_issues(extraction)
    report: dict[str, Any] = {
        "format": FORMAT,
        "source": {"path": str(pdf), "sha256": source_sha, "bytes": len(data)},
        "pages": len(extraction["pages"]),
        "gate": gate.as_dict() | {"diagnosis": diagnose(extraction, gate, languages)},
        "commands": {"extract": command},
        "tools": tools,
        "options": {
            "languages": languages,
            "tessdata": str(tessdata) if tessdata else None,
            "visual_check": visual_check,
            "min_score": min_score,
            "schema": str(schema) if schema else "not requested",
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.mkdir()  # exclusive reservation
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        (stage / "sources").mkdir()
        (stage / "sources" / source_sha).write_bytes(data)
        write_json(stage / "extraction.json", extraction)
        if not gate.passed:
            report["status"] = "gated"
            report["outputs"] = {"tei": None, "tf": None}
            finish(stage, output, report, issues)
            return report
        title = pdf_title(pdf, runner)
        built = build_tei(extraction, title, tools)
        issues += built.issues
        tei_path = stage / "document.tei.xml"
        tei_path.write_bytes(built.xml)
        manifest = tei_convert(
            [],
            stage / "tei-to-tf",
            Policy(milestones="pages", facsimile="zones"),
            schema=schema,
            sources=[Source(tei_path.name, tei_path.as_uri(), built.xml)],
        )
        graph = manifest["graph"]
        checked = verify(stage / "tei-to-tf" / "tf", graph, built.elements)
        issues += checked["mismatches"]
        for issue in issues:
            if issue.xml_id and issue.tf_node is None:
                issue.tf_node = checked["node_of"].get(issue.xml_id)
        failed = bool(checked["mismatches"])
        report["status"] = (
            "verification_failed"
            if failed
            else (
                "converted_with_issues"
                if any(i.severity in {"error", "warning"} for i in issues)
                else "converted"
            )
        )
        report["title"] = title
        report["languages"] = built.languages
        report["verification"] = {
            "tf_load": "passed",
            "tei_to_tf_exact_text": "passed",
            "checked": checked["checked"],
            "mismatches": len(checked["mismatches"]),
        }
        report["mapping"] = {
            "elements": [
                {
                    "page": m.page,
                    "index": m.index,
                    "kind": m.kind,
                    "xml_id": m.xml_id,
                    "tei_tag": m.tei_tag,
                    "status": m.status,
                    "tf_node": checked["node_of"].get(m.xml_id),
                }
                for m in built.elements
            ],
            "tf": {
                "max_slot": graph["max_slot"],
                "max_node": graph["max_node"],
                "pages": graph.get("pages"),
                "attribute_features": graph["attribute_features"],
            },
        }
        report["outputs"] = {
            "tei": "document.tei.xml",
            "tf": "tei-to-tf/tf",
            "tei_to_tf_manifest": "tei-to-tf/manifest.json",
        }
        finish(stage, output, report, issues)
        return report
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        output.rmdir()
        raise


def finish(stage: Path, output: Path, report: dict[str, Any], issues: list[Issue]) -> None:
    issues.sort(
        key=lambda i: (
            SEVERITY_ORDER[i.severity],
            i.page or 0,
            i.element_index if i.element_index is not None else -1,
            i.word_index if i.word_index is not None else -1,
            i.code,
        )
    )
    counts: dict[str, int] = {}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    report["issue_counts"] = counts
    report["issues"] = [i.as_dict() for i in issues]
    write_reports(stage, report)
    hashes = {
        str(path.relative_to(stage)): digest(path)
        for path in sorted(stage.rglob("*"))
        if path.is_file()
    }
    write_json(stage / "checksums.json", hashes)
    os.replace(stage, output)
