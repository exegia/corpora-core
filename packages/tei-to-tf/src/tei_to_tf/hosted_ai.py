"""Bounded AI SDK subprocess adapter; proposals never bypass local validators."""

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from .model import ConversionError


class HostedAI:
    def __init__(self, bridge: Path, model: str, max_requests: int = 100):
        if not bridge.is_file() or not 1 <= max_requests <= 10000:
            raise ConversionError("AI bridge must exist; request budget must be 1..10000")
        self.bridge = bridge.resolve()
        self.model = model
        self.remaining = max_requests
        self.cache: dict[str, dict[str, Any]] = {}

    def request(self, task: str, context: str, issues: list[dict[str, Any]]) -> dict[str, Any]:
        payload = json.dumps(dict(task=task, model=self.model, context=context, issues=issues))
        key = hashlib.sha256(payload.encode()).hexdigest()
        if key in self.cache:
            return self.cache[key]
        if self.remaining == 0:
            return {"error": "request_budget_exhausted"}
        self.remaining -= 1
        try:
            process = subprocess.run(
                ["node", str(self.bridge)],
                input=payload,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=70,
                check=False,
            )
            result = json.loads(process.stdout)
            if not isinstance(result, dict) or ("error" not in result and not valid_result(result)):
                return {"error": "invalid_response"}
            if "error" not in result:
                self.cache[key] = result
            return result
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {"error": "bridge_unavailable"}


def valid_result(result: dict[str, Any]) -> bool:
    edits = result.get("edits")
    return (
        isinstance(edits, list)
        and len(edits) <= 100
        and all(
            isinstance(e, dict)
            and type(e.get("id")) is int
            and e["id"] >= 0
            and all(isinstance(e.get(k), str) and e[k] for k in ("before", "after", "reason"))
            for e in edits
        )
    )


def structural_proposal(
    data: bytes, issues: list[dict[str, Any]], ai: Any
) -> tuple[bytes, list[dict[str, Any]]]:
    """Accept closing-tag edits and bare ampersand escaping, never text reconstruction."""
    if ai is None:
        return data, []
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data, []
    result = ai.request("xml", text, issues[:100])
    for issue in issues:
        issue["ai_status"] = result.get("error", "reviewed")
        issue["ai_model"] = result.get("model")
    if "error" in result or not valid_result(result):
        return data, []
    edits = sorted(result["edits"], key=lambda e: e["id"], reverse=True)
    last = len(text)
    changes = []
    protected = [
        (m.start(), m.end())
        for m in re.finditer(r"<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>", text, re.S)
    ]
    if "<!DOCTYPE" in text:
        return data, []
    for edit in edits:
        start, before, after = edit["id"], edit["before"], edit["after"]
        end = start + len(before)
        closing = re.fullmatch(r"</[\w:.-]+\s*>", before) and re.fullmatch(r"</[\w:.-]+\s*>", after)
        ampersand = (
            before == "&"
            and after == "&amp;"
            and not re.match(r"&(?:#\d+|#x[\da-fA-F]+|[\w:.-]+);", text[start:])
        )
        if (
            end > last
            or text[start:end] != before
            or not (closing or ampersand)
            or any(start < b and end > a for a, b in protected)
        ):
            return data, []
        text = text[:start] + after + text[end:]
        last = start
        changes.append(
            dict(
                code="ai_xml_repair",
                start=start,
                before=before,
                after=after,
                reason=edit["reason"],
                ai_model=result.get("model"),
            )
        )
    return text.encode(), changes


def suggest_spelling(tree: Any, issues: list[dict[str, Any]], checker: Any, ai: Any) -> None:
    nodes = {tree.getpath(n): n for n in tree.iter()}
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for issue in issues:
        if issue.get("validation_kind") == "purpose":
            issue["ai_status"] = "purpose_validation"
            continue
        if issue["code"] == "language_unresolved":
            issue["ai_status"] = "language_unresolved"
            continue
        if issue["score"] == 20:
            continue
        issue["ai_status"] = "not_configured" if ai is None else "pending"
        if issue["score"] == 90:
            if issue.get("replacement"):
                issue["suggestions"] = list(
                    dict.fromkeys([issue["replacement"], *issue.get("suggestions", [])])
                )
            issue["replacement"] = None
            issue["repairable"] = False
        if ai is not None and issue["field"] in {"text", "tail"}:
            groups.setdefault((issue["path"], issue["field"]), []).append(issue)
    for (path, field), findings in groups.items():
        for offset in range(0, len(findings), 100):
            batch = findings[offset : offset + 100]
            request = [
                dict(
                    id=i,
                    text=d["text"],
                    score=d["score"],
                    role=d["role"],
                    language=d["language"],
                    suggestions=d.get("suggestions", []),
                )
                for i, d in enumerate(batch)
            ]
            result = ai.request("spelling", getattr(nodes[path], field), request)
            for issue in batch:
                issue["ai_status"] = result.get("error", "reviewed")
                issue["ai_model"] = result.get("model")
            if "error" in result or not valid_result(result):
                continue
            ids = [e["id"] for e in result["edits"]]
            if len(ids) != len(set(ids)):
                continue
            for edit in result["edits"]:
                if edit["id"] >= len(batch):
                    continue
                issue = batch[edit["id"]]
                if edit["before"] != issue["text"] or edit["after"] == edit["before"]:
                    continue
                after = edit["after"]
                if any(c.isalpha() for c in edit["before"]) and not any(c.isalpha() for c in after):
                    continue
                if not after.strip():
                    continue
                if len(after) > max(128, len(edit["before"]) * 2) or any(
                    c in after for c in "<>\r\n"
                ):
                    continue
                issue["ai_suggestion"] = after
                issue["ai_reason"] = edit["reason"]
                # Capitalization cannot be used to evade a dictionary failure.
                check = checker.check(
                    after.lower(),
                    "metadata",
                    issue.get("locale_hint") or issue["language"]["locale"],
                )
                if issue["score"] == 90 and issue["role"] != "corpus" and not check["diagnostics"]:
                    issue["replacement"] = after
                    issue["repairable"] = True
