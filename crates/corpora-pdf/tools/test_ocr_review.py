"""No network, credentials, model downloads, or private fixtures required."""

import copy
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import ocr_review as ocr


class MarkComparisonTest(unittest.TestCase):
    def test_canonical_equivalence_and_rtl(self):
        self.assertEqual(ocr.compare("ἄ", "α\u0313\u0301")["codepoint_edits"], 0)
        self.assertEqual(ocr.compare("לֹא", "לֹא")["codepoint_edits"], 0)
        self.assertGreater(ocr.compare("לא", "אל")["codepoint_edits"], 0)

    def test_missing_and_moved_marks_have_base_locations(self):
        result = ocr.compare("אָא", "אאָ", True)
        self.assertTrue(result["confirmed_discrepancy"])
        marks = result["mark_discrepancies"]
        self.assertEqual(marks[0]["reference_base_index"], 0)
        self.assertEqual(marks[0]["missing"], ["U+05B8"])
        self.assertEqual(marks[1]["candidate_base_index"], 1)
        self.assertEqual(marks[1]["inserted"], ["U+05B8"])
        self.assertFalse(ocr.compare("לֹא", "לא")["confirmed_discrepancy"])

    def test_substitution_and_base_deletion(self):
        marks = ocr.compare("לֹא", "לָא")["mark_discrepancies"]
        self.assertEqual(marks[0]["kind"], "substitution")
        self.assertEqual(marks[0]["missing"], ["U+05B9"])
        self.assertEqual(
            ocr.compare("לֹא", "א")["mark_discrepancies"][0]["candidate_base_index"],
            None,
        )


class PipelineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pdf = self.root / "source.pdf"
        self.pdf.write_bytes(b"%PDF-1.4 synthetic")
        self.region = {
            "id": "one",
            "page": 1,
            "bounds": [0, 0, 0.5, 0.5],
            "script": "hebrew",
            "raw_text": "",
            "required_marks": "\u05b9",
            "reference": {"text": "לֹא", "status": "image_verified"},
        }
        self.manifest = {
            "source_sha256": ocr.digest(self.pdf.read_bytes()),
            "regions": [self.region],
        }
        self.hosted = Mock(return_value="לא")
        self.render = Mock(return_value=b"synthetic-image")
        version = patch.object(
            ocr.subprocess,
            "run",
            return_value=Mock(stderr=b"Poppler-test\n", stdout=b""),
        )
        version.start()
        self.addCleanup(version.stop)

    def run_pipeline(self, **kwargs):
        options = {
            "pdf": self.pdf,
            "manifest": self.manifest,
            "output": self.root / "report.json",
            "cache": self.root / "cache",
            "provider": "mistral",
            "max_calls": 1,
            "render_region": self.render,
            "hosted_recognize": self.hosted,
        }
        options.update(kwargs)
        return ocr.run(**options)

    def test_cache_and_missing_script_hint_keep_source_and_location(self):
        before = self.pdf.read_bytes()
        result = self.run_pipeline()
        item = result["regions"][0]
        self.assertEqual(item["raw_text"], "")
        self.assertEqual(item["script"], "hebrew")
        self.assertEqual(item["bounds"], self.region["bounds"])
        self.assertIsNone(item["missing_marks"])
        self.assertTrue(item["comparison"]["confirmed_discrepancy"])
        self.assertEqual(result["calls"], 1)
        second = self.run_pipeline()
        self.assertEqual(second["calls"], 0)
        self.assertTrue(second["regions"][0]["cache_hit"])
        self.hosted.assert_called_once()
        self.assertEqual(self.pdf.read_bytes(), before)
        self.assertEqual((self.root / "report.json").stat().st_mode & 0o777, 0o600)

    def test_changed_reference_reuses_recognition_but_recomputes_comparison(self):
        self.run_pipeline()
        self.region["reference"]["text"] = "לא"
        result = self.run_pipeline()
        self.assertEqual(result["calls"], 0)
        self.assertEqual(result["regions"][0]["comparison"]["codepoint_edits"], 0)

    def test_changed_geometry_invalidates_cache_and_cap_stops_requests(self):
        self.run_pipeline()
        self.region["bounds"] = [0.1, 0.1, 0.9, 0.9]
        self.assertEqual(self.run_pipeline()["calls"], 1)
        other = copy.deepcopy(self.region)
        other.update(id="two", page=2)
        third = copy.deepcopy(other)
        third.update(id="three", page=3)
        self.manifest["regions"] += [other, third]
        result = self.run_pipeline()
        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["regions"][-1]["status"], "budget_exhausted")

    def test_source_mismatch_rejected_before_render_or_upload(self):
        self.manifest["source_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "mismatch"):
            self.run_pipeline()
        self.render.assert_not_called()
        self.hosted.assert_not_called()

    def test_invalid_inputs(self):
        for changes in (
            {"bounds": [0, 0, float("nan"), 1]},
            {"page": True},
            {"script": "unknown"},
            {"required_marks": "a"},
        ):
            with self.subTest(changes=changes):
                manifest = copy.deepcopy(self.manifest)
                manifest["regions"][0].update(changes)
                with self.assertRaises(ValueError):
                    self.run_pipeline(manifest=manifest)
        with self.assertRaises(ValueError):
            self.run_pipeline(max_calls=0)
        self.hosted.assert_not_called()

    def test_failed_provider_does_not_leak_secrets_or_retry(self):
        self.hosted.side_effect = ValueError("PRIVATE-SECRET")
        report = self.run_pipeline()
        self.assertEqual(report["regions"][0]["status"], "recognition_failed")
        self.assertNotIn("PRIVATE-SECRET", json.dumps(report))
        self.hosted.assert_called_once()
        self.assertFalse((self.root / "cache").exists())

    def test_bad_provider_output_is_not_cached(self):
        self.hosted.return_value = {"bad": "response"}
        self.assertEqual(
            self.run_pipeline()["regions"][0]["status"], "recognition_failed"
        )

    def test_output_cannot_overwrite_source(self):
        with self.assertRaisesRegex(ValueError, "overwrite"):
            self.run_pipeline(output=self.pdf)
        self.hosted.assert_not_called()

    def test_model_alphabet_failure_precedes_render(self):
        model = self.root / "model.safetensors"
        meta = {
            "model": {
                "codec": {
                    c: [i] for i, c in enumerate("אבגדהוזחטיךכלםמןנסעףפץצקרשת", 1)
                }
            }
        }
        header = json.dumps(
            {"__metadata__": {"kraken_meta": json.dumps(meta)}}
        ).encode()
        model.write_bytes(struct.pack("<Q", len(header)) + header)
        with self.assertRaisesRegex(ValueError, "U\\+05B9"):
            self.run_pipeline(provider="local", model=model, kraken=model)
        self.render.assert_not_called()
        meta["model"]["codec"]["\u05b9"] = [3]
        header = json.dumps(
            {"__metadata__": {"kraken_meta": json.dumps(meta)}}
        ).encode()
        model.write_bytes(struct.pack("<Q", len(header)) + header)
        self.assertTrue(ocr.alphabet(model, "\u05b9")["passed"])
        self.region["script"] = "greek"
        with self.assertRaisesRegex(ValueError, "base alphabet for greek"):
            self.run_pipeline(provider="local", model=model, kraken=model)
        self.render.assert_not_called()


class HostedAdapterTest(unittest.TestCase):
    def test_request_contract_and_secret_free_error(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"pages":[{"markdown":"candidate"}]}'
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.dict(os.environ, {"MISTRAL_API_KEY": "test-only"}),
            patch.object(ocr.urllib.request, "build_opener", return_value=opener),
        ):
            self.assertEqual(ocr.hosted(b"image"), "candidate")
            request = opener.open.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(body["model"], "mistral-ocr-2512")
            self.assertEqual(body["document"]["type"], "image_url")
            self.assertEqual(request.full_url, "https://api.mistral.ai/v1/ocr")
            opener.open.side_effect = OSError("test-only")
            with self.assertRaisesRegex(ValueError, "no retry") as error:
                ocr.hosted(b"image")
            self.assertNotIn("test-only", str(error.exception))


if __name__ == "__main__":
    unittest.main()
