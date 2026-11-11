"""Located conversion issues and their suggested fixes."""

from dataclasses import asdict, dataclass
from typing import Any

LOW_WORD_CONFIDENCE = 0.6
LOW_ELEMENT_SCORE = 0.8
PAGE_SCAN_COVERAGE = 0.9
OCR_REVIEW = "crates/corpora-pdf/tools/ocr_review.py --provider vercel"
QA_BROWSER = "tests/browser/build_pdf_review.py"

# code -> (severity, stage, suggestion). Severity: error | warning | info.
CATALOG: dict[str, tuple[str, str, str]] = {
    "low_visual_agreement": (
        "warning",
        "extraction",
        "Compare the page image with the text layer in the PDF QA browser "
        f"({QA_BROWSER}). If the text layer is wrong, correct it in the TEI file and "
        "convert the TEI again. If OCR is wrong, install the correct Tesseract model "
        "and rerun with --languages.",
    ),
    "visual_check_unavailable": (
        "warning",
        "extraction",
        "Install Tesseract and the languages named in --languages so the text layer "
        "can be compared with the rendered page; this page counts as 0 in the score.",
    ),
    "low_ocr_confidence": (
        "warning",
        "extraction",
        "Rescan at 300 DPI or more, or rerun with the correct --languages/--tessdata "
        f"model. Review low-confidence regions with {OCR_REVIEW}.",
    ),
    "no_text_found": (
        "warning",
        "extraction",
        "If the page shows text, check the OCR language models; if it is blank, no "
        "action is needed.",
    ),
    "visual_semantics_unverified": (
        "warning",
        "extraction",
        "Images and graphs are not transcribed. Add a TEI figDesc by hand if their "
        "content matters, then convert the TEI again.",
    ),
    "page_scan_image": (
        "info",
        "extraction",
        "This image is the page scan itself; its transcription is the OCR text.",
    ),
    "script_marks_review": (
        "warning",
        "extraction",
        "Check these marks against the page image. Local OCR often drops vowel and "
        f"accent marks; compare a candidate from {OCR_REVIEW} with an image-verified "
        "reference before correcting the TEI.",
    ),
    "script_model_unverified": (
        "warning",
        "extraction",
        "No validated recognizer exists for this script; treat the text as a draft "
        "and verify it against the page image.",
    ),
    "low_element_score": (
        "warning",
        "extraction",
        "Read this line against the page image at the given bounds; correct the TEI if it differs.",
    ),
    "low_confidence_word": (
        "info",
        "extraction",
        "Check this word against the page image at the given bounds.",
    ),
    "unscored_page": (
        "error",
        "extraction",
        "The page has text but no visual score. Install Tesseract with the needed "
        "languages and rerun without --no-visual-check.",
    ),
    "mark_not_located": (
        "warning",
        "conversion",
        "The formatting or link text was not found in its line; it is kept in "
        "extraction.json but not in TEI/TF. Add the hi/ref element in the TEI by hand.",
    ),
    "mark_overlap_dropped": (
        "warning",
        "conversion",
        "Two marks overlap without nesting, which XML cannot express; the later one "
        "was dropped. Add it in the TEI by hand if it matters.",
    ),
    "words_text_mismatch": (
        "warning",
        "conversion",
        "OCR words do not join to the line text, so word elements were not created "
        "for this line. Report this extraction as an engine bug.",
    ),
    "xml_incompatible_character": (
        "error",
        "conversion",
        "The PDF text contains a character XML 1.0 cannot store; it was replaced by "
        "U+FFFD in TEI/TF. Check the original glyph in the page image and correct "
        "the TEI.",
    ),
    "whitespace_element_omitted": (
        "info",
        "conversion",
        "A whitespace-only line carries no text and was left out of TEI/TF.",
    ),
    "visual_not_in_tf": (
        "info",
        "conversion",
        "Images have no text, so they are zero-width TEI figures and not TF nodes; "
        "their bounds stay in the TEI facsimile and TF document JSON.",
    ),
    "table_structure_heuristic": (
        "info",
        "conversion",
        "Rows were inferred from cell positions; spanning cells are not "
        "reconstructed. Check the table against the page image.",
    ),
    "verification_mismatch": (
        "error",
        "verification",
        "TF does not match the extraction here. Do not use this output; report the "
        "case with extraction.json and document.tei.xml.",
    ),
}


@dataclass
class Issue:
    code: str
    message: str
    page: int | None = None
    element_index: int | None = None
    word_index: int | None = None
    bounds: dict[str, float] | None = None
    text: str | None = None
    xml_id: str | None = None
    tf_node: int | None = None
    severity: str = ""
    stage: str = ""
    suggestion: str = ""

    def __post_init__(self) -> None:
        severity, stage, suggestion = CATALOG[self.code]
        self.severity = self.severity or severity
        self.stage = self.stage or stage
        self.suggestion = self.suggestion or suggestion

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def element_id(page: int, index: int, word: int | None = None) -> str:
    return f"p{page}e{index}" + ("" if word is None else f"w{word}")


def excerpt(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_page_scan(page: dict[str, Any], element: dict[str, Any]) -> bool:
    b = element["bounds"]
    area = page["width"] * page["height"]
    return bool(
        page["method"] == "ocr"
        and element["kind"] == "image"
        and area > 0
        and b["width"] * b["height"] >= PAGE_SCAN_COVERAGE * area
    )


def extraction_issues(extraction: dict[str, Any]) -> list[Issue]:
    """Issues reported by the engine plus low-evidence lines and words."""
    pages = {p["number"]: p for p in extraction["pages"]}
    issues = []
    for finding in extraction.get("findings", []):
        page = pages.get(finding.get("page"))
        code = finding["code"]
        if code == "visual_semantics_unverified" and page:
            visuals = [
                (i, e)
                for i, e in enumerate(page["elements"])
                if e["kind"] in {"image", "graph_candidate"}
            ]
            for index, element in visuals:
                issues.append(
                    Issue(
                        "page_scan_image" if is_page_scan(page, element) else code,
                        f"{element['kind']} on page {page['number']}",
                        page["number"],
                        index,
                        bounds=element["bounds"],
                        xml_id=element_id(page["number"], index),
                    )
                )
            continue
        if code not in CATALOG:
            code = "low_visual_agreement" if "agree" in code else "no_text_found"
        issues.append(Issue(code, finding["message"], finding.get("page")))
    for review in extraction.get("script_review", []):
        code = review["code"] if review["code"] in CATALOG else "script_marks_review"
        issues.append(
            Issue(
                code,
                review["message"],
                review["page"],
                review["element_index"],
                review.get("word_index"),
                review["bounds"],
                excerpt(review["raw_text"]),
                element_id(review["page"], review["element_index"], review.get("word_index")),
            )
        )
    for page in extraction["pages"]:
        number = page["number"]
        has_text = any(e["text"].strip() for e in page["elements"])
        if has_text and not page.get("extraction_score"):
            issues.append(
                Issue("unscored_page", f"page {number} text has no visual evidence", number)
            )
        for index, element in enumerate(page["elements"]):
            score = element.get("extraction_score")
            if score and score["value"] < LOW_ELEMENT_SCORE and element["text"].strip():
                issues.append(
                    Issue(
                        "low_element_score",
                        f"{score['basis']} {score['value']:.2f} for this line",
                        number,
                        index,
                        bounds=element["bounds"],
                        text=excerpt(element["text"]),
                        xml_id=element_id(number, index),
                    )
                )
            for word_index, word in enumerate(element.get("words", [])):
                if word["confidence"] < LOW_WORD_CONFIDENCE:
                    issues.append(
                        Issue(
                            "low_confidence_word",
                            f"OCR confidence {word['confidence']:.2f}",
                            number,
                            index,
                            word_index,
                            word["bounds"],
                            word["text"],
                            element_id(number, index, word_index),
                        )
                    )
    return issues
