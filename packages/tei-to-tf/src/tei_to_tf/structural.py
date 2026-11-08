"""Rust structural reports and guarded preview edits; diagnosis belongs to core."""

import hashlib
import re
from typing import Any

from .model import ConversionError
from .parse import secure_tree


def _report(checker: Any, text: str, source_id: str) -> dict[str, Any]:
    report = checker.structural(text, source_id)
    return validate_core_report(report, text, source_id)


def validate_core_report(report: Any, text: str, source_id: str) -> dict[str, Any]:
    """Validate the shared source binding used by structural and purpose receipts."""
    if (
        not isinstance(report, dict)
        or type(report.get("schema_version")) is not int
        or report["schema_version"] != 1
        or report.get("source_id") != source_id
        or report.get("source_sha256") != hashlib.sha256(text.encode()).hexdigest()
        or not isinstance(report.get("diagnostics"), list)
    ):
        raise ConversionError("Invalid or stale core structural report; rebuild the Rust bridge")
    for issue in report["diagnostics"]:
        if (
            not isinstance(issue, dict)
            or issue.get("category") != "structural"
            or type(issue.get("blocking")) is not bool
            or not isinstance(issue.get("code"), str)
            or not isinstance(issue.get("message"), str)
            or not isinstance(issue.get("locations"), list)
            or not isinstance(issue.get("suggestions"), list)
        ):
            raise ConversionError("Invalid core structural diagnostic")
    return report


def structural_diagnostics(data: bytes, checker: Any, source_id: str) -> list[dict[str, Any]]:
    """Diagnose exactly this candidate through core, without applying proposals."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConversionError("Core structural quality checks require UTF-8 XML input") from error
    report = _report(checker, text, source_id)
    return [_legacy(issue, report) for issue in report["diagnostics"]]


def _legacy(issue: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Keep browser receipt fields alongside the complete source-bound core diagnostic."""
    result = dict(
        code=issue["code"],
        message=issue["message"],
        blocking=issue["blocking"],
        repairable=False,
        source_id=report["source_id"],
        source_sha256=report["source_sha256"],
        core_schema_version=report["schema_version"],
        core_diagnostic=issue,
        suggestions=[
            s["message"]
            for s in issue["suggestions"]
            if isinstance(s, dict) and isinstance(s.get("message"), str)
        ],
    )
    if issue["locations"]:
        start = issue["locations"][0]["start"]
        result.update(line=start["line"], column=start["column"], start=start["scalar"])
    return result


def _safe_edit(issue: dict[str, Any], text: str) -> dict[str, Any] | None:
    """Retain the converter's bounded lexical policy; proposals are not approval."""
    for suggestion in issue["suggestions"]:
        if not isinstance(suggestion, dict) or suggestion.get("applicability") not in {
            "automatic",
            "review",
        }:
            continue
        edits = suggestion.get("edits")
        if not isinstance(edits, list) or len(edits) != 1 or not isinstance(edits[0], dict):
            continue
        edit = edits[0]
        before, after = edit.get("before"), edit.get("after")
        if not isinstance(before, str) or not isinstance(after, str):
            continue
        lexical = (
            issue["code"] == "xml_bare_ampersand" and before == "&" and after == "&amp;"
        ) or (
            issue["code"] == "xml_tag_case"
            and re.fullmatch(r"</[\w:.-]+>", before) is not None
            and re.fullmatch(r"</[\w:.-]+>", after) is not None
            and before.lower() == after.lower()
            and before != after
            and suggestion["applicability"] == "automatic"
        )
        if not lexical:
            continue
        try:
            start, end = edit["range"]["start"], edit["range"]["end"]
            for position in (start, end):
                if any(
                    type(position.get(k)) is not int for k in ("byte", "scalar", "line", "column")
                ):
                    raise ValueError("Invalid coordinate")
                byte, scalar = position["byte"], position["scalar"]
                if not 0 <= scalar <= len(text) or byte != len(text[:scalar].encode()):
                    raise ValueError("Byte/scalar coordinates disagree")
                prefix = text[:scalar]
                if (position["line"], position["column"]) != (
                    prefix.count("\n") + 1,
                    len(prefix.rsplit("\n", 1)[-1]) + 1,
                ):
                    raise ValueError("Line/column coordinates disagree")
            if not 0 <= start["scalar"] <= end["scalar"] <= len(text):
                raise ValueError("Invalid range")
            if text[start["scalar"] : end["scalar"]] != before:
                raise ValueError("Stale expected text")
        except (KeyError, TypeError, ValueError) as error:
            raise ConversionError("Invalid or stale core structural edit") from error
        return edit
    return None


def structural_preview(
    data: bytes, checker: Any, source_id: str = "<input>"
) -> tuple[bytes, list[dict[str, Any]]]:
    """Apply core lexical proposals to a disposable preview, rolling back partial failures.

    Every edit uses its own source snapshot. Rust and the projection parser must both
    accept the complete preview. No independent Python structural diagnosis is used.
    """
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ConversionError("Core structural quality checks require UTF-8 XML input") from error
    findings: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    for _ in range(33):
        report = _report(checker, text, source_id)
        issues = report["diagnostics"]
        if not issues:
            # Independent projection compatibility check, not a source of repair proposals.
            secure_tree(text.encode())
            return text.encode(), changes
        findings.extend(_legacy(issue, report) for issue in issues)
        if len(changes) == 32 or len(issues) != 1 or not issues[0]["blocking"]:
            break
        edit = _safe_edit(issues[0], text)
        if edit is None:
            break
        start, end = edit["range"]["start"]["scalar"], edit["range"]["end"]["scalar"]
        change = dict(
            findings[-1],
            before=edit["before"],
            after=edit["after"],
            start=start,
            end=end,
            repairable=True,
        )
        changes.append(change)
        text = text[:start] + edit["after"] + text[end:]
    if changes:
        findings[0]["proposed_partial_fixes"] = changes
    return data, findings
