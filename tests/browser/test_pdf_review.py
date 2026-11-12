"""Exercise the real PDF engine through the browser review builder."""

import importlib.util
import json
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
from xml.etree import ElementTree
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
        ), patch.object(MODULE, "render_page", return_value="mock-page.png"):
            site = Path(directory)
            MODULE.build(source, site, "eng", tei=False)
            review = json.loads((site / "review.json").read_text())
            self.assertIsNone(review["tei_url"])
            self.assertEqual(review["units"][0]["findings"], [])
            self.assertEqual(review["units"][1]["findings"], [finding])
            self.assertIsNone(review["units"][1]["findings"][0]["missing_marks"])

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
            self.assertEqual(len(extraction["pages"]), len(review["units"]))
            for page, unit in zip(extraction["pages"], review["units"]):
                png = (site / unit["source_image_url"]).read_bytes()
                self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
                width, height = struct.unpack(">II", png[16:24])
                self.assertAlmostEqual(width, page["width"], delta=1)
                self.assertAlmostEqual(height, page["height"], delta=1)
            self.assertEqual(extraction["pages"][1]["method"], "ocr")
            self.assertIn("Original source", (site / "index.html").read_text())
            index = (site / "index.html").read_text()
            self.assertIn("TEI rendering", index)
            self.assertRegex(index, r'src="review\.js\?v=[0-9a-f]{12}"')
            # The TEI is pdf-to-tf's, built from this extraction: line ids match the cards.
            self.assertEqual(review["tei_url"], "document.tei.xml")
            tei = ElementTree.parse(site / "document.tei.xml").getroot()
            ns = {"t": "http://www.tei-c.org/ns/1.0", "xml": "http://www.w3.org/XML/1998/namespace"}
            head = tei.find(".//t:head[@xml:id='p1e0']", ns)
            self.assertIsNotNone(head)
            self.assertEqual("".join(head.itertext()), "Sample Document")
            self.assertIn("color-scheme:dark", (site / "review.css").read_text())


if __name__ == "__main__":
    unittest.main()
