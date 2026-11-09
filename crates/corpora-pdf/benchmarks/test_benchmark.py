"""Independent metric and region-selection checks; no private PDFs required."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import benchmark as b


def element(text, x, y):
    return {"text": text, "kind": "paragraph",
            "bounds": {"x": x, "y": y, "width": 10, "height": 10}}


def manifest():
    return {"version": 1, "samples": [{"id": "sample", "page": 1,
            "path": "source.pdf", "sha256": "0" * 64,
            "regions": [{"id": "left", "box": [0, 0, .5, 1],
                         "reference": "A B", "reference_status": "human_verified"},
                        {"id": "right", "box": [.5, 0, 1, 1],
                         "reference": "C", "reference_status": "human_verified"}],
            "order": [["left", "right"]]}]}


class BenchmarkTests(unittest.TestCase):
    def test_edit_rates_count_substitutions_deletions_and_insertions(self):
        self.assertEqual(b.measure("cat", "cut")["character_edits"], 1)
        self.assertEqual(b.measure("cat", "")["cer"], 1)
        self.assertEqual(b.measure("a", "aaaa")["cer"], 3)
        self.assertEqual(b.measure("one two three", "one four")["word_edits"], 2)

    def test_nfc_and_whitespace_do_not_remove_vowel_marks_or_punctuation(self):
        self.assertTrue(b.measure("café\nword", "cafe\u0301  word")["exact"])
        self.assertFalse(b.measure("לֹא", "לא")["exact"])
        self.assertFalse(b.measure("word.", "word")["exact"])
        self.assertFalse(b.measure("Word", "word")["exact"])

    def test_empty_reference_is_rejected(self):
        with self.assertRaises(ValueError):
            b.measure(" \n", "text")

    def test_region_keeps_engine_order_and_detects_column_interleaving(self):
        page = {"width": 100, "height": 100,
                "elements": [element("A", 0, 0), element("C", 60, 0), element("B", 0, 20)]}
        result = b.evaluate(page, manifest()["samples"][0])
        self.assertEqual(result["cer"], 0)
        self.assertFalse(result["order"][0]["passed"])
        self.assertEqual(result["regions"][0]["element_indices"], [0, 2])

    def test_missing_region_is_an_error_not_a_perfect_score(self):
        result = b.evaluate({"width": 100, "height": 100, "elements": []},
                            manifest()["samples"][0])
        self.assertEqual(result["cer"], 1)
        self.assertFalse(result["order"][0]["passed"])

    def test_merged_cells_are_alignment_failures_not_false_ocr_measurements(self):
        merged = element("A C", 0, 0)
        merged["bounds"]["width"] = 100
        result = b.evaluate({"width": 100, "height": 100, "elements": [merged]},
                            manifest()["samples"][0])
        self.assertIsNone(result["cer"])
        self.assertEqual(result["ambiguous_regions"], 2)

    def test_invalid_manifest_rejected(self):
        for field, value in [("page", 0), ("id", "../escape"), ("sha256", "unknown")]:
            data = manifest()
            data["samples"][0][field] = value
            with self.assertRaises(ValueError):
                b.validate(data)
        for box in [[0, 0, 2, 1], [0, 0, 0, 1], [0, float("nan"), 1, 1]]:
            data = manifest()
            data["samples"][0]["regions"][0]["box"] = box
            with self.assertRaises(ValueError):
                b.validate(data)

    def test_duplicate_samples_and_unreviewed_status_are_explicit(self):
        data = manifest()
        b.validate(data)
        data["samples"].append(copy.deepcopy(data["samples"][0]))
        with self.assertRaises(ValueError):
            b.validate(data)
        data = manifest()
        del data["samples"][0]["regions"][0]["reference_status"]
        with self.assertRaises(ValueError):
            b.validate(data)

    def test_source_hash_mismatch_prevents_subprocesses_and_output(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "source.pdf").write_bytes(b"different source")
            path = root / "manifest.json"
            path.write_text(json.dumps(manifest()))
            with patch.object(b, "run") as run:
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    b.benchmark(path, root / "output", "eng")
                run.assert_not_called()
            self.assertFalse((root / "output").exists())

    def test_reference_html_is_escaped(self):
        sample = manifest()["samples"][0]
        sample["regions"][0]["reference"] = "<script>alert(1)</script>"
        measured = b.evaluate({"width": 100, "height": 100, "elements": []}, sample)
        measured["engine_score"] = None
        page = b.report_html([{"sample": sample, "modes": {"native": measured}}])
        self.assertNotIn("<script>", page)
        self.assertIn("&lt;script&gt;", page)

    def test_explicit_model_directory_records_exact_model_hashes(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eng.traineddata").write_bytes(b"english fixture")
            (root / "heb.traineddata").write_bytes(b"hebrew fixture")
            listing = f'List of available languages in "{root}" (2):\neng\nheb\n'.encode()
            with patch.object(b, "run", return_value=listing) as run:
                result = b.model_provenance("eng+heb", root)
                run.assert_called_once_with(["tesseract", "--list-langs", "--tessdata-dir", root])
            self.assertEqual(result["models"]["heb"]["sha256"], hashlib.sha256(b"hebrew fixture").hexdigest())

    def test_missing_requested_model_is_not_silently_omitted_from_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "eng.traineddata").write_bytes(b"english fixture")
            listing = f'List of available languages in "{root}" (1):\neng\n'.encode()
            with patch.object(b, "run", return_value=listing):
                with self.assertRaisesRegex(ValueError, "not installed.*heb"):
                    b.model_provenance("eng+heb", root)


if __name__ == "__main__":
    unittest.main()
