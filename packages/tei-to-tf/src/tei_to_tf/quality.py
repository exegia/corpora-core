"""Audited validate → repair → revalidate pipeline; originals are never modified."""

import hashlib
import json
import select
import subprocess
from pathlib import Path
from typing import Any

from lxml import etree

from .acquire import Limits, acquire
from .convert import convert, validate_schema, write_json
from .hosted_ai import structural_proposal, suggest_spelling
from .model import ConversionError, Policy, Source
from .parse import parse, secure_tree
from .structural import structural_diagnostics
from .structural import structural_preview as structural_preview

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"


class SpellProcess:
    """One JSON-lines Matchum process, caching dictionaries across segments."""

    def __init__(self, executable: Path, dictionaries: Path | None = None):
        self.process = subprocess.Popen(
            [str(executable.resolve()), *([str(dictionaries.resolve())] if dictionaries else [])],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )

    def detect(self, text: str, locale: str | None) -> dict[str, Any]:
        return self.request(text, "corpus", locale, True)

    def check(self, text: str, role: str, locale: str | None) -> dict[str, Any]:
        return self.request(text, role, locale, False)

    def request(
        self, text: str, role: str, locale: str | None, detect_only: bool
    ) -> dict[str, Any]:
        return self.send(dict(text=text, role=role, locale=locale, detect_only=detect_only))

    def structural(self, text: str, source_id: str) -> dict[str, Any]:
        return self.send(dict(operation="structure", source_id=source_id, text=text))

    def send(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.process.stdin is not None and self.process.stdout is not None
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 120)[0]:
            raise ConversionError("Matchum response timed out")
        line = self.process.stdout.readline()
        if not line:
            raise ConversionError("Matchum process exited without a response")
        response: dict[str, Any] = json.loads(line)
        if "error" in response:
            raise ConversionError(f"Core engine unavailable: {response['error']}")
        return response

    def close(self) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()


def text_segments(tree: etree._ElementTree) -> list[tuple[Any, str, str, str | None]]:
    """Disjoint text/tail fields; markup and machine-readable attributes are not prose."""
    result = []

    def classify(owner: Any) -> tuple[str, str | None]:
        chain = [owner, *owner.iterancestors()]
        tags = {etree.QName(n).localname for n in chain if isinstance(n.tag, str)}
        locale = next((n.get(XML_LANG) for n in chain if n.get(XML_LANG)), None)
        role = (
            "metadata"
            if tags & {"teiHeader", "titlePage", "docTitle", "docAuthor", "docImprint"}
            else "footnote"
            if "note" in tags
            else (
                "frontmatter" if "front" in tags else "corpus" if "body" in tags else "additional"
            )
        )
        if any(
            n.get("type", "").lower() in {"toc", "contents", "tableofcontents", "table-of-contents"}
            for n in chain
        ):
            role = "additional"
        return role, locale

    def visit(node: Any) -> None:
        if isinstance(node.tag, str) and node.text:
            role, language = classify(node)
            result.append((node, "text", role, language))
        for child in node:
            visit(child)
            if child.tail:
                role, language = classify(node)
                result.append((child, "tail", role, language))

    visit(tree.getroot())
    return result


def inspect_tree(
    tree: etree._ElementTree, checker: Any, locale: str | None, corrections: dict[str, str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    segments = text_segments(tree)
    # Prefer declared document language; otherwise infer from the body rather than publishers.
    declared = tree.getroot().get(XML_LANG)
    sample = " ".join(getattr(node, field) for node, field, role, _ in segments if role == "corpus")
    detection = checker.detect(sample, locale or declared)
    fallback = locale or declared or detection["locale"]
    # Preserve a French reform hint rather than collapsing it to fr-FR in the response.
    if detection.get("dictionary") == "fr_FR_90":
        fallback = "fr-FR-1990"
    diagnostics = []
    blocks = {
        "p",
        "l",
        "head",
        "title",
        "author",
        "publisher",
        "date",
        "name",
        "note",
        "lem",
        "rdg",
        "orig",
        "reg",
        "sic",
        "corr",
        "abbr",
        "expan",
        "ab",
        "item",
        "addrLine",
        "pubPlace",
        "idno",
        "resp",
    }
    groups: dict[tuple[str, str, str | None], list[tuple[Any, str]]] = {}
    for node, field, role, hint in segments:
        owner = node if field == "text" else node.getparent()
        block = next(
            (
                n
                for n in [owner, *owner.iterancestors()]
                if isinstance(n.tag, str) and etree.QName(n).localname in blocks
            ),
            owner,
        )
        groups.setdefault((tree.getpath(block), role, hint), []).append((node, field))
    for (path, role, hint), fields in groups.items():
        text = "".join(getattr(node, field) for node, field in fields)
        if not text.strip():
            continue
        block_node = next(n for n in tree.iter() if tree.getpath(n) == path)
        heading = any(
            isinstance(n.tag, str) and etree.QName(n).localname in {"head", "title", "docTitle"}
            for n in [block_node, *block_node.iterancestors()]
        )
        report = checker.check(text, "heading" if heading else role, locale or hint or fallback)
        for finding in report["diagnostics"]:
            issue = dict(
                finding, path=path, field="mixed_content", role=role, language=report["language"]
            )
            score = 20 if heading or issue["text"][:1].isupper() else 60 if role == "corpus" else 90
            issue.update(score=score, blocking=score == 90, review_optional=score < 90)
            if score < 90:
                issue["replacement"] = None
            replacement = corrections.get(issue["text"]) if score == 90 else None
            if replacement:
                verification = checker.check(replacement, role, locale or hint or fallback)
                if verification["passed"]:
                    issue["replacement"] = replacement
                    issue["reason"] = issue.get("reason", "") + "; explicit correction map"
            # A correction must fit within one original XML field; never flatten markup.
            offset = 0
            for node, field in fields:
                size = len(getattr(node, field))
                if offset <= issue["start"] and issue["end"] <= offset + size:
                    issue.update(
                        path=tree.getpath(node),
                        field=field,
                        start=issue["start"] - offset,
                        end=issue["end"] - offset,
                    )
                    break
                offset += size
            else:
                issue["replacement"] = None
                issue["reason"] = (
                    issue.get("reason", "")
                    + "; word spans XML fields, requires markup-aware review"
                )
            issue["repairable"] = issue.get("replacement") is not None
            diagnostics.append(issue)
    return diagnostics, detection


def repair_spelling(
    tree: etree._ElementTree, diagnostics: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    changes = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for issue in diagnostics:
        if (
            issue.get("replacement") is not None
            and issue["role"] != "corpus"
            and issue["score"] == 90
        ):
            grouped.setdefault((issue["path"], issue["field"]), []).append(issue)
    # Resolve getpath's generated namespace prefix without relying on source prefix names.
    nodes = {tree.getpath(n): n for n in tree.iter()}
    for (path, field), issues in grouped.items():
        node = nodes[path]
        value = getattr(node, field)
        last = len(value)
        for issue in sorted(issues, key=lambda i: i["start"], reverse=True):
            start, end = issue["start"], issue["end"]
            if end > last or value[start:end] != issue["text"]:
                raise ConversionError("Overlapping/stale spelling repair")
            value = value[:start] + issue["replacement"] + value[end:]
            last = start
            changes.append(
                {
                    "path": path,
                    "field": field,
                    "start": start,
                    "before": issue["text"],
                    "after": issue["replacement"],
                }
            )
        setattr(node, field, value)
    return changes


def quality_convert(
    inputs: list[str],
    output: Path,
    checker: Any,
    policy: Policy | None = None,
    locale: str | None = None,
    corrections: dict[str, str] | None = None,
    revision: str | None = None,
    schema: Path | None = None,
    sources: list[Source] | None = None,
    limits: Limits | None = None,
    ai: Any = None,
    max_cycles: int = 3,
) -> dict[str, Any]:
    """Retain all three pass receipts, repaired copies and originals, even when blocked."""
    if not 1 <= max_cycles <= 10:
        raise ConversionError("Repair cycles must be 1..10")
    policy = policy or Policy()
    acquired = sources if sources is not None else acquire(inputs, limits=limits, revision=revision)
    if output.exists():
        raise ConversionError(f"Output already exists: {output}")
    output.mkdir(parents=True)
    (output / "originals").mkdir()
    (output / "repaired").mkdir()
    report: dict[str, Any] = {"status": "running", "documents": [], "offset_unit": "Unicode scalar"}
    accepted = []
    try:
        for index, source in enumerate(acquired):
            digest = hashlib.sha256(source.data).hexdigest()
            (output / "originals" / digest).write_bytes(source.data)
            row: dict[str, Any] = {
                "source": source.origin,
                "source_sha256": digest,
                "pass_1": [],
                "pass_2": [],
                "pass_3": [],
                "status": "blocked",
            }
            report["documents"].append(row)
            if Path(source.name).suffix.lower() not in {
                ".xml",
                ".tei",
                ".odd",
                ".rng",
                ".xsd",
            } and not source.data.lstrip().startswith(b"<"):
                row["status"] = "repository-metadata"
                continue
            candidate = source.data
            row["cycles"] = []
            seen = set()
            for _cycle_number in range(max_cycles):
                cycle: dict[str, Any] = {"pass_1": [], "pass_2": [], "pass_3": []}
                row["cycles"].append(cycle)
                signature = hashlib.sha256(candidate).hexdigest()
                seen.add(signature)
                preview, structural = structural_preview(candidate, checker, source.origin)
                cycle["pass_1"].extend(structural)
                for issue in cycle["pass_1"]:
                    issue["ai_status"] = "not_configured" if ai is None else "pending"
                if structural:
                    proposed, ai_changes = structural_proposal(candidate, cycle["pass_1"], ai)
                    if ai_changes:
                        preview = proposed
                        cycle["pass_2"].extend(ai_changes)
                    elif preview != candidate:
                        cycle["pass_2"].extend(structural)
                try:
                    cycle["pass_3"] = structural_diagnostics(preview, checker, source.origin)
                    if any(d["blocking"] for d in cycle["pass_3"]):
                        raise ConversionError("Core structural validation failed")
                    tree = secure_tree(preview)
                    prepared = Source(source.name, source.origin, preview, source.revision)
                    parsed, classification = parse(prepared, policy)
                    if classification["classification"] != "tei" or not any(
                        d.text.strip() for d in parsed
                    ):
                        row["status"] = "metadata-only"
                        break
                    if schema:
                        validate_schema(prepared, schema)
                    diagnostics, detection = inspect_tree(tree, checker, locale, corrections or {})
                    suggest_spelling(tree, diagnostics, checker, ai)
                    row["language"] = detection
                    cycle["pass_1"].extend(diagnostics)
                    corpus_before = "".join(
                        getattr(n, f) for n, f, role, _ in text_segments(tree) if role == "corpus"
                    )
                    changes = repair_spelling(tree, diagnostics)
                    cycle["pass_2"].extend(changes)
                    repaired = (
                        etree.tostring(tree, encoding="utf-8", xml_declaration=True)
                        if changes
                        else preview
                    )
                    prepared = Source(source.name, source.origin, repaired, source.revision)
                    cycle["pass_3"] = structural_diagnostics(repaired, checker, source.origin)
                    if any(d["blocking"] for d in cycle["pass_3"]):
                        raise ConversionError("Core structural revalidation failed")
                    final_tree = secure_tree(repaired)
                    corpus_after = "".join(
                        getattr(n, f)
                        for n, f, role, _ in text_segments(final_tree)
                        if role == "corpus"
                    )
                    if corpus_before != corpus_after:
                        raise ConversionError("Repair changed primary corpus text")
                    cycle["pass_3"], _ = inspect_tree(
                        final_tree, checker, locale, corrections or {}
                    )
                    suggest_spelling(final_tree, cycle["pass_3"], checker, ai)
                    parse(prepared, policy)
                    if schema:
                        validate_schema(prepared, schema)
                    for receipt_cycle in row["cycles"]:
                        for change in receipt_cycle["pass_2"]:
                            change["validated"] = True
                    name = f"{index + 1:04d}.xml"
                    (output / "repaired" / name).write_bytes(repaired)
                    row["repaired_file"] = f"repaired/{name}"
                    row["repaired_sha256"] = hashlib.sha256(repaired).hexdigest()
                    row["spell_coordinate_basis"] = "pass_3 uses repaired XML text/tail fields"
                    candidate = repaired
                    if not any(d["blocking"] for d in cycle["pass_3"]):
                        row["status"] = "passed"
                        accepted.append(prepared)
                except (ConversionError, etree.LxmlError) as error:
                    diagnostic = {
                        "code": "validation_error",
                        "blocking": True,
                        "repairable": False,
                        "message": str(error),
                    }
                    cycle["pass_3"].append(diagnostic)
                    if not cycle["pass_1"]:
                        cycle["pass_1"].append(dict(diagnostic))
                    # Conversion/schema errors receive AI review with the same guards.
                    candidate, changes = structural_proposal(preview, cycle["pass_3"], ai)
                    cycle["pass_2"].extend(changes)
                for change in cycle["pass_2"]:
                    change.setdefault("validated", False)
                row["pass_1"] = row["cycles"][0]["pass_1"]
                row["pass_2"] = [d for c in row["cycles"] for d in c["pass_2"]]
                row["pass_3"] = cycle["pass_3"]
                if row["status"] == "passed":
                    break
                if hashlib.sha256(candidate).hexdigest() in seen:
                    row["stop_reason"] = "No validated progress; unresolved issues remain blocking"
                    break
            else:
                row["stop_reason"] = "Repair cycle limit reached; unresolved issues remain blocking"
            row["pass_1"] = row["cycles"][0]["pass_1"]
            row["pass_2"] = [d for c in row["cycles"] for d in c["pass_2"]]
            row["pass_3"] = row["cycles"][-1]["pass_3"]
        if accepted:
            manifest = convert(
                [], output / "corpus", policy=policy, sources=accepted, schema=schema
            )
            report["converted_documents"] = manifest["documents"]
        report["passed"] = sum(r["status"] == "passed" for r in report["documents"])
        report["blocked"] = sum(r["status"] == "blocked" for r in report["documents"])
        report["metadata_only"] = sum(
            r["status"] in {"metadata-only", "repository-metadata"} for r in report["documents"]
        )
        report["status"] = "passed" if report["blocked"] == 0 and accepted else "blocked"
        if not accepted:
            report["reason"] = "No TEI reading content passed quality validation"
        return report
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        write_json(output / "quality-report.json", report)
