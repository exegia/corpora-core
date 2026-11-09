"""A reversible display projection over immutable source character slots."""

from typing import Any

HORIZONTAL = frozenset(" \t\v\f\u00a0")
LINEBREAK = frozenset("\r\n\u2028\u2029")
ZERO_WIDTH_LAYOUT = frozenset("\u200b\ufeff")
LAYOUT_WHITESPACE = HORIZONTAL | LINEBREAK | ZERO_WIDTH_LAYOUT
PRESERVE_TAGS = frozenset({"pre", "code", "textarea"})


def normalize_slots(text: str, elements: list[dict[str, Any]]) -> tuple[list[str], list[int]]:
    """Return one display value per source scalar and source-to-display offsets.

    Source slots, element spans, and exact text remain unchanged. A run of layout
    whitespace becomes one space or one newline; edge runs disappear. Explicit
    preformatted spans retain every source character.
    """
    protected = sorted(
        (element["start"], element["end"])
        for element in elements
        if element["tag"] in PRESERVE_TAGS
        or element["attributes"].get("xml:space") == "preserve"
        or element["attributes"].get("space") == "preserve"
    )
    merged: list[tuple[int, int]] = []
    for start, end in protected:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    values = [""] * len(text)
    interval = 0
    index = 0
    while index < len(text):
        while interval < len(merged) and index >= merged[interval][1]:
            interval += 1
        guarded = interval < len(merged) and merged[interval][0] <= index
        if guarded or text[index] not in LAYOUT_WHITESPACE:
            values[index] = text[index]
            index += 1
            continue
        start = index
        first_linebreak: int | None = None
        first_horizontal: int | None = None
        while index < len(text):
            if interval < len(merged) and index >= merged[interval][0]:
                break
            if text[index] not in LAYOUT_WHITESPACE:
                break
            if first_linebreak is None and text[index] in LINEBREAK:
                first_linebreak = index
            if first_horizontal is None and text[index] in HORIZONTAL:
                first_horizontal = index
            index += 1
        if start > 0 and index < len(text):
            if first_linebreak is not None:
                values[first_linebreak] = "\n"
            elif first_horizontal is not None:
                values[first_horizontal] = " "
    offsets = [0]
    for value in values:
        offsets.append(offsets[-1] + len(value))
    return values, offsets


def annotate_scope(scope: dict[str, Any], assets: list[dict[str, Any]]) -> list[str]:
    """Add display text and offsets while keeping source text and offsets."""
    values, offsets = normalize_slots(scope["text"], scope["elements"])
    scope["reading_text"] = "".join(values)
    for element in scope["elements"]:
        element["reading_start"] = offsets[element["start"]]
        element["reading_end"] = offsets[element["end"]]
    for asset in assets:
        asset["reading_offset"] = offsets[asset["text_offset"]]
    return values
