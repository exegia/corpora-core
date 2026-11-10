"""Exercise the real PDF engine through the browser review builder."""

import importlib.util
import json
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("build_pdf_review", Path(__file__).with_name("build_pdf_review.py"))
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PdfReviewTest(unittest.TestCase):
    def test_script_findings_reach_the_correct_page(self) -> None:
        source = ROOT / "crates/corpora-pdf/tests/fixtures/mixed.pdf"
        finding = {"page": 2, "code": "script_marks_review",
                   "message": "Page 2, element 0: inspect Hebrew pointing",
                   "missing_marks": None, "scalar_range": [0, 2]}
        pages = [{"number": n, "method": "ocr", "language": None,
                  "language_reliable": False, "extraction_score": None, "elements": []}
                 for n in (1, 2)]
        output = {"pages": pages, "findings": [], "script_review": [finding]}
        with tempfile.TemporaryDirectory() as directory, patch.object(
            MODULE.subprocess, "run", return_value=Mock(stdout=json.dumps(output))
        ):
            site = Path(directory)
            MODULE.build(source, site, "eng")
            review = json.loads((site / "review.json").read_text())
            self.assertEqual(review["units"][0]["findings"], [])
            self.assertEqual(review["units"][1]["findings"], [finding])

    def test_site_contains_source_and_extraction(self) -> None:
        source = ROOT / "crates/corpora-pdf/tests/fixtures/mixed.pdf"
        with tempfile.TemporaryDirectory() as directory:
            site = Path(directory)
            MODULE.build(source, site, "eng")
            extraction = json.loads((site / "result.json").read_text(encoding="utf-8"))
            review = json.loads((site / "review.json").read_text(encoding="utf-8"))
            self.assertEqual((site / "source.pdf").read_bytes(), source.read_bytes())
            self.assertEqual(extraction["pages"][0]["elements"][0]["text"], "Sample Document")
            self.assertEqual(extraction["pages"][0]["elements"][0]["kind"], "h1")
            self.assertEqual(review["units"][0]["source_url"], "source.pdf#page=1&toolbar=0")
            self.assertEqual(review["units"][1]["source_url"], "source.pdf#page=2&toolbar=0")
            self.assertEqual(extraction["pages"][1]["method"], "ocr")
            self.assertIn("Original source", (site / "index.html").read_text())
            self.assertIn("color-scheme:dark", (site / "review.css").read_text())


if __name__ == "__main__":
    unittest.main()
