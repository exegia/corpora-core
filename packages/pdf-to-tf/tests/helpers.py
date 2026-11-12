"""Synthetic corpora-pdf extractions."""

import hashlib
from pathlib import Path
from typing import Any

PDF_BYTES = b"%PDF-1.4 synthetic test bytes\n"
SHA = hashlib.sha256(PDF_BYTES).hexdigest()


def bounds(x: float, y: float, w: float = 200, h: float = 12) -> dict[str, float]:
    return {"x": x, "y": y, "width": w, "height": h}


def el(
    kind: str,
    text: str,
    y: float,
    *,
    x: float = 100,
    w: float = 200,
    h: float = 12,
    marks: list[dict[str, Any]] | None = None,
    words: list[dict[str, Any]] | None = None,
    score: float | None = 1.0,
    table_id: int | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "text": text,
        "bounds": bounds(x, y, w, h),
        "marks": marks or [],
        "section_path": [],
        "table_id": table_id,
        "extraction_score": None
        if score is None
        else {"value": score, "basis": "text_layer_ocr_agreement"},
        **({"words": words} if words else {}),
    }


def ocr_words(text: str, y: float, confidence: float = 0.97) -> list[dict[str, Any]]:
    return [
        {"text": t, "bounds": bounds(100 + 40 * i, y, 35, 12), "confidence": confidence}
        for i, t in enumerate(text.split(" "))
    ]


def page(
    number: int,
    elements: list[dict[str, Any]],
    *,
    method: str = "text_layer",
    score: float | None = 1.0,
    language: str | None = "eng",
    reliable: bool = True,
) -> dict[str, Any]:
    basis = "ocr_word_confidence" if method == "ocr" else "text_layer_ocr_agreement"
    return {
        "number": number,
        "width": 918.0,
        "height": 1188.0,
        "language": language,
        "language_reliable": reliable,
        "method": method,
        "elements": elements,
        "extraction_score": None if score is None else {"value": score, "basis": basis},
    }


def extraction(pages: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "source_path": "/fixed/test.pdf",
        "source_sha256": SHA,
        "pages": pages,
        "findings": [],
        **extra,
    }


def write_pdf(tmp: Path) -> Path:
    path = tmp / "test.pdf"
    path.write_bytes(PDF_BYTES)
    return path


def sample() -> dict[str, Any]:
    """Two pages: headings, marks, list, table, OCR words, image and a weak word."""
    line = "Ἐν ἀρχῇ ἦν"
    words = ocr_words(line, 100)
    words[1]["confidence"] = 0.41
    return extraction(
        [
            page(
                1,
                [
                    el(
                        "h1",
                        "Title",
                        50,
                        h=20,
                        marks=[{"kind": "bold", "text": "Title", "target": None}],
                    ),
                    el(
                        "paragraph",
                        "First line with a link here.",
                        80,
                        marks=[
                            {"kind": "link", "text": "link", "target": "https://example.org/x"},
                            {"kind": "italic", "text": "First", "target": None},
                        ],
                    ),
                    el("paragraph", "second line.", 93),
                    el("paragraph", "New paragraph.", 140),
                    el("h2", "Part", 180, h=16),
                    el("list_item", "1. One", 200),
                    el("list_item", "2. Two", 213),
                    el("table_cell", "Name", 240, w=50, table_id=1),
                    el("table_cell", "Value", 240, x=200, w=50, table_id=1),
                    el("table_cell", "Alpha", 254, w=50, table_id=1),
                    el("table_cell", "42", 254, x=200, w=50, table_id=1),
                    el("paragraph", "   ", 300),
                    el("image", "", 400, w=300, h=200, score=None),
                ],
            ),
            page(
                2,
                [el("paragraph", line, 100, words=words, score=0.9)],
                method="ocr",
                score=0.97,
                language="ell",
                reliable=True,
            ),
        ],
        findings=[{"page": 1, "code": "visual_semantics_unverified", "message": "image"}],
    )
