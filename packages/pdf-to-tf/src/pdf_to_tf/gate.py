"""Conversion score gate.

The document score weights each page's visual evidence score by the number of
non-whitespace characters extracted from that page:

    score = sum(page_score * page_chars) / sum(page_chars)

A page that has text but no visual score contributes 0: its text could not be
checked against the rendered page. Pages without text carry no weight; they are
reported as issues instead. The gate passes only when ``score > min_score``.

The page scores come from ``corpora-pdf``: mean Tesseract word confidence on OCR
pages, or token overlap between the text layer and OCR of the rendered page.
Neither is accuracy measured against a reference transcription.
"""

from dataclasses import dataclass, field
from typing import Any

DEFAULT_MIN_SCORE = 0.95


@dataclass(frozen=True)
class PageScore:
    page: int
    method: str
    characters: int
    score: float | None
    basis: str | None


@dataclass(frozen=True)
class Gate:
    min_score: float
    score: float
    passed: bool
    characters: int
    pages: list[PageScore] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "min_score": self.min_score,
            "rule": "score > min_score",
            "score": self.score,
            "passed": self.passed,
            "weighted_characters": self.characters,
            "definition": (
                "Character-weighted mean of corpora-pdf page evidence scores; "
                "pages with text but no visual score count as 0. "
                "Not accuracy against a reference transcription."
            ),
            "pages": [
                {
                    "page": p.page,
                    "method": p.method,
                    "characters": p.characters,
                    "score": p.score,
                    "basis": p.basis,
                }
                for p in self.pages
            ],
        }


def page_characters(page: dict[str, Any]) -> int:
    return sum(len("".join(e["text"].split())) for e in page["elements"])


def evaluate(extraction: dict[str, Any], min_score: float = DEFAULT_MIN_SCORE) -> Gate:
    if not 0 < min_score < 1:
        raise ValueError("min_score must be between 0 and 1 (exclusive)")
    pages = []
    weighted = 0.0
    total = 0
    for page in extraction["pages"]:
        chars = page_characters(page)
        evidence = page.get("extraction_score")
        value = float(evidence["value"]) if evidence else None
        pages.append(
            PageScore(
                page["number"],
                page["method"],
                chars,
                value,
                evidence["basis"] if evidence else None,
            )
        )
        total += chars
        weighted += (value or 0.0) * chars
    score = weighted / total if total else 0.0
    return Gate(min_score, score, total > 0 and score > min_score, total, pages)


def diagnose(extraction: dict[str, Any], gate: Gate, languages: str) -> list[str]:
    """One plain cause and next step for each page that pulls the score down."""
    requested = set(languages.split("+"))
    pages = {p["number"]: p for p in extraction["pages"]}
    notes = []
    for item in gate.pages:
        if not item.characters or (item.score is not None and item.score > gate.min_score):
            continue
        page = pages[item.page]
        detected = page.get("language")
        hint = ""
        if detected and detected not in requested:
            hint = (
                f" Detected language `{detected}` is not in --languages `{languages}`; "
                f"install its Tesseract model and add `+{detected}`."
            )
        if item.score is None:
            notes.append(
                f"Page {item.page}: text could not be checked against the page image "
                f"(OCR unavailable).{hint or ' Install Tesseract and the needed models.'}"
            )
        elif item.method == "text_layer":
            notes.append(
                f"Page {item.page}: text layer agrees with page OCR at {item.score:.0%}."
                + (hint or " Compare the page image with the text layer; it may be corrupt.")
            )
        else:
            notes.append(
                f"Page {item.page}: mean OCR word confidence is {item.score:.0%}."
                + (hint or " Rescan at 300 DPI or more, or use a better-matching model.")
            )
    return notes
