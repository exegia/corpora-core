"""Source-bound Rust purpose receipts; Python never invents typed-field approval."""

from typing import Any

from lxml import etree

from .model import ConversionError
from .structural import _legacy, validate_core_report

TEI = "http://www.tei-c.org/ns/1.0"


def _validate_ranges(text: str, ranges: list[Any]) -> None:
    """Check all native byte/scalar/line coordinates in one scan of the source."""
    points: dict[int, tuple[int, int, int]] = {}
    for span in ranges:
        if not isinstance(span, dict):
            raise ConversionError("Invalid core purpose range")
        for edge in ("start", "end"):
            p = span.get(edge)
            if not isinstance(p, dict) or any(
                type(p.get(k)) is not int for k in ("byte", "scalar", "line", "column")
            ):
                raise ConversionError("Invalid core purpose position")
            expected = (p["scalar"], p["line"], p["column"])
            if p["byte"] in points and points[p["byte"]] != expected:
                raise ConversionError("Inconsistent core purpose coordinates")
            points[p["byte"]] = expected
        if span["start"]["byte"] > span["end"]["byte"]:
            raise ConversionError("Reversed core purpose range")
    byte, line, column, matched = 0, 1, 1, 0
    for scalar, ch in enumerate(text):
        if byte in points:
            if points[byte] != (scalar, line, column):
                raise ConversionError("Core purpose coordinates do not match the source")
            matched += 1
        byte += len(ch.encode())
        if ch == "\n":
            line, column = line + 1, 1
        else:
            column += 1
    if byte in points:
        if points[byte] != (len(text), line, column):
            raise ConversionError("Core purpose EOF coordinates do not match the source")
        matched += 1
    if matched != len(points):
        raise ConversionError("Core purpose range is outside UTF-8 boundaries")


def inspect_purposes(
    tree: etree._ElementTree,
    checker: Any,
    data: bytes,
    source_id: str,
    expected_document_id: str | None,
    allow_no_namespace: bool,
) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]]]:
    """Bind typed fields to the parsed tree, keeping blocked fields out of spelling AI."""
    nodes: dict[tuple[int, ...], Any] = {}
    expected_paths: set[tuple[int, ...]] = set()
    stack: list[tuple[Any, tuple[int, ...], bool, bool]] = [(tree.getroot(), (), False, False)]
    while stack:
        node, locator, in_metadata, inside_field = stack.pop()
        nodes[locator] = node
        name = etree.QName(node)
        tei = name.namespace == TEI or allow_no_namespace and name.namespace is None
        metadata = (
            in_metadata
            or tei
            and name.localname in {"teiHeader", "titlePage", "docTitle", "docAuthor", "docImprint"}
        )
        is_field = tei and metadata and not inside_field and name.localname in {"date", "idno"}
        if is_field:
            expected_paths.add(locator)
        for index, child in enumerate(c for c in node if isinstance(c.tag, str)):
            stack.append((child, (*locator, index), metadata, inside_field or is_field))
    if not expected_paths:
        return [], set(), []
    text = data.decode("utf-8")
    report = validate_core_report(
        checker.purpose(text, source_id, expected_document_id, allow_no_namespace), text, source_id
    )
    if (
        type(report.get("policy_version")) is not int
        or report["policy_version"] != 1
        or "expected_document_id" not in report
        or report["expected_document_id"] != expected_document_id
        or report.get("allow_no_namespace") is not allow_no_namespace
    ):
        raise ConversionError("Invalid or stale core purpose policy receipt")
    if not isinstance(report.get("fields"), list):
        raise ConversionError("Core purpose receipts unavailable; rebuild the Rust bridge")
    diagnostics: list[dict[str, Any]] = []
    excluded: set[str] = set()
    audit: list[dict[str, Any]] = []
    used: set[int] = set()
    received_paths: set[tuple[int, ...]] = set()
    ranges = [r for d in report["diagnostics"] for r in d["locations"]]
    for field in report["fields"]:
        if (
            not isinstance(field, dict)
            or not isinstance(field.get("element_path"), list)
            or any(type(i) is not int for i in field["element_path"])
        ):
            raise ConversionError("Invalid core purpose element locator")
        locator = tuple(field["element_path"])
        if locator not in expected_paths or locator in received_paths:
            raise ConversionError("Unexpected or duplicate core purpose receipt")
        received_paths.add(locator)
        node = nodes.get(locator)
        if node is None:
            raise ConversionError("Core purpose field does not match the parsed element")
        name = etree.QName(node)
        if field.get("name") != name.localname or field.get("namespace") != (name.namespace or ""):
            raise ConversionError("Core purpose field does not match the parsed element")
        if name.namespace != TEI and not (allow_no_namespace and name.namespace is None):
            raise ConversionError("Core purpose receipt targets a foreign element")
        if field.get("purpose") != {"date": "date", "idno": "identifier"}.get(name.localname):
            raise ConversionError("Invalid core field purpose")
        if field.get("value") != "".join(
            value.decode("utf-8") if isinstance(value, bytes) else value
            for value in node.itertext()
        ):
            raise ConversionError("Core purpose value/scope differs from parsed metadata")
        if not isinstance(field.get("value_ranges"), list) or not isinstance(
            field.get("range"), dict
        ):
            raise ConversionError("Missing core purpose source ranges")
        ranges.extend([field["range"], *field["value_ranges"]])
        path = tree.getpath(node)
        if path in excluded:
            raise ConversionError("Duplicate core purpose receipt")
        status, diagnostic_index = field.get("status"), field.get("diagnostic_index")
        if status == "blocked":
            if (
                type(diagnostic_index) is not int
                or not 0 <= diagnostic_index < len(report["diagnostics"])
                or diagnostic_index in used
                or not report["diagnostics"][diagnostic_index]["blocking"]
            ):
                raise ConversionError("Missing blocking purpose diagnostic")
            issue = _legacy(report["diagnostics"][diagnostic_index], report)
            issue.update(
                path=path,
                field="structured",
                role="metadata",
                score=None,
                validation_kind="purpose",
                purpose=field["purpose"],
                text=field["value"],
                purpose_policy=dict(
                    version=report["policy_version"],
                    expected_document_id=expected_document_id,
                    allow_no_namespace=allow_no_namespace,
                ),
            )
            diagnostics.append(issue)
            used.add(diagnostic_index)
        elif status != "validated" or diagnostic_index is not None:
            raise ConversionError("Invalid core purpose status")
        excluded.add(path)
        audit.append(
            dict(
                field,
                path=path,
                source_id=source_id,
                source_sha256=report["source_sha256"],
                expected_document_id=expected_document_id,
                core_schema_version=report["schema_version"],
                policy_version=report["policy_version"],
                allow_no_namespace=allow_no_namespace,
            )
        )
    if received_paths != expected_paths:
        raise ConversionError("Incomplete core purpose field coverage")
    if used != set(range(len(report["diagnostics"]))):
        raise ConversionError("Unassociated core purpose diagnostics")
    _validate_ranges(text, ranges)
    return diagnostics, excluded, audit
