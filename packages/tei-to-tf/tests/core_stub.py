"""Offline protocol fixtures for adapter tests, not a production structural checker.

Only known broken test tokens receive candidates. Native parsing/coordinates are
tested in Rust and the optional real-bridge acceptance test.
"""

import hashlib
import re

from tei_to_tf.model import ConversionError
from tei_to_tf.parse import secure_tree


def position(text, scalar):
    prefix = text[:scalar]
    return dict(
        byte=len(prefix.encode()),
        scalar=scalar,
        line=prefix.count("\n") + 1,
        column=len(prefix.rsplit("\n", 1)[-1]) + 1,
    )


def core_report(text, source_id):
    report = dict(
        schema_version=1,
        source_id=source_id,
        source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        diagnostics=[],
    )
    try:
        secure_tree(text.encode())
        return report
    except ConversionError:
        pass
    candidates = [
        (m.start(), m[0], "&amp;", "xml_bare_ampersand")
        for m in re.finditer(r"&(?!#[0-9]+;|#x[0-9a-fA-F]+;|[A-Za-z_:][\w:.-]*;)", text)
    ]
    for before in ("</AUTHOR>", "</A>", "</MANIFEST>", "</P>"):
        if before in text:
            candidates.append((text.index(before), before, before.lower(), "xml_tag_case"))
    suggestions, locations = [], []
    code = "xml_parse_error"
    if candidates:
        start, before, after, code = min(candidates)
        location = dict(start=position(text, start), end=position(text, start + len(before)))
        locations = [location]
        suggestions = [
            dict(
                message="Fixture lexical correction",
                applicability=("review" if code == "xml_bare_ampersand" else "automatic"),
                edits=[dict(range=location, before=before, after=after)],
            )
        ]
    report["diagnostics"] = [
        dict(
            code=code,
            category="structural",
            severity="error",
            blocking=True,
            certainty="certain",
            score=None,
            message="Fixture XML error",
            locations=locations,
            suggestions=suggestions,
        )
    ]
    return report
