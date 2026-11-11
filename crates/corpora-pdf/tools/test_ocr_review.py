"""No network, credentials, model downloads, or private fixtures required."""

import copy
import io
import json
import os
import struct
import tempfile
import unittest
import urllib.error
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
            "gateway_check": Mock(return_value={"status": "eligible"}),
            "read_page_boxes": Mock(
                return_value={"media_box": [0, 0, 612, 792], "crop_box": [0, 0, 612, 792]}
            ),
        }
        options.update(kwargs)
        return ocr.run(**options)

    def test_report_records_rendered_page_frame_once_per_page(self):
        boxes = Mock(
            return_value={"media_box": [0, 0, 612, 828], "crop_box": [0, 18, 612, 810]}
        )
        other = copy.deepcopy(self.region)
        other.update(id="two")
        self.manifest["regions"].append(other)
        report = self.run_pipeline(read_page_boxes=boxes, max_calls=2)
        boxes.assert_called_once_with(self.pdf, 1)
        frame = report["regions"][0]["page_frame"]
        self.assertEqual(frame["rendered_box"], "media_box")
        self.assertTrue(frame["crop_box_differs"])
        self.assertEqual(frame["crop_box"], [0, 18, 612, 810])
        self.assertEqual(report["regions"][1]["page_frame"], frame)

    def test_gateway_isolated_cache_budget_and_usage(self):
        self.run_pipeline()  # A Mistral cache entry must not satisfy Gateway.
        recognize = Mock(
            return_value={"text": "לֹא", "metadata": {"usage": {"total_tokens": 20}}}
        )
        other = copy.deepcopy(self.region)
        other.update(id="two", page=2)
        self.manifest["regions"].append(other)
        first = self.run_pipeline(provider="vercel", gateway_recognize=recognize)
        self.assertEqual(first["calls"], 1)
        self.assertEqual(first["regions"][0]["candidate_text"], "לֹא")
        self.assertEqual(first["regions"][1]["status"], "budget_exhausted")
        self.manifest["regions"].pop()
        second = self.run_pipeline(provider="vercel", gateway_recognize=recognize)
        self.assertEqual(second["calls"], 0)
        self.assertEqual(
            second["regions"][0]["recognition_metadata"]["usage"]["total_tokens"], 20
        )
        recognize.assert_called_once_with(b"synthetic-image", ocr.gateway_ocr.MODEL)
        with patch.object(ocr.gateway_ocr, "PROMPT", "changed instructions"):
            changed = self.run_pipeline(provider="vercel", gateway_recognize=recognize)
            self.assertEqual(changed["calls"], 1)

    def test_mistral_accounting_survives_cache_without_credentials(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "pages": [{"markdown": "לֹא"}],
                "model": "mistral-ocr-2512-completion",
                "usage_info": {"pages_processed": 1, "doc_size_bytes": 123},
            }
        ).encode()
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.dict(os.environ, {"MISTRAL_API_KEY": "test-only"}),
            patch.object(ocr.urllib.request, "build_opener", return_value=opener),
        ):
            first = self.run_pipeline(hosted_recognize=ocr.hosted_response)
        item = first["regions"][0]
        self.assertEqual(first["calls"], 1)
        self.assertEqual(item["candidate_text"], "לֹא")
        self.assertEqual(item["output_format"], "markdown")
        self.assertEqual(item["status"], "review_required")
        self.assertIsNone(item["missing_marks"])
        self.assertEqual(
            item["recognition_metadata"],
            {
                "requested_model": ocr.MODEL,
                "reported_model": "mistral-ocr-2512-completion",
                "usage_info": {"pages_processed": 1, "doc_size_bytes": 123},
            },
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                ocr.urllib.request,
                "build_opener",
                side_effect=AssertionError("network forbidden"),
            ),
        ):
            second = self.run_pipeline(hosted_recognize=ocr.hosted_response)
        self.assertEqual(second["calls"], 0)
        self.assertTrue(second["regions"][0]["cache_hit"])
        self.assertEqual(
            second["regions"][0]["recognition_metadata"], item["recognition_metadata"]
        )
        opener.open.assert_called_once()

    def test_mistral_rejected_output_retains_usage_without_cache_or_retry(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "pages": [
                    {"markdown": "PRIVATE_PARTIAL"},
                    {"markdown": "PRIVATE_OTHER"},
                ],
                "model": ocr.MODEL,
                "usage_info": {
                    "pages_processed": 2,
                    "doc_size_bytes": None,
                    "secret": "PRIVATE",
                },
            }
        ).encode()
        opener = Mock()
        opener.open.return_value = response
        other = copy.deepcopy(self.region)
        other.update(id="two", page=2)
        self.manifest["regions"].append(other)
        with (
            patch.dict(os.environ, {"MISTRAL_API_KEY": "test-only"}),
            patch.object(ocr.urllib.request, "build_opener", return_value=opener),
        ):
            report = self.run_pipeline(hosted_recognize=ocr.hosted_response)
        item = report["regions"][0]
        self.assertEqual(item["status"], "recognition_failed")
        self.assertIsNone(item["candidate_text"])
        self.assertEqual(item["raw_text"], self.region["raw_text"])
        self.assertEqual(
            item["recognition_metadata"]["usage_info"], {"pages_processed": 2}
        )
        self.assertEqual(item["error_code"], "hosted_ocr_failed")
        self.assertEqual(report["regions"][1]["status"], "budget_exhausted")
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertNotIn("test-only", json.dumps(report))
        self.assertFalse((self.root / "cache").exists())
        self.assertEqual(report["calls"], 1)
        opener.open.assert_called_once()

    def test_legacy_mistral_cache_without_metadata_needs_no_request(self):
        first = self.run_pipeline()
        entry = self.root / "cache" / (first["regions"][0]["cache_key"] + ".json")
        cached = json.loads(entry.read_text())
        cached.pop("recognition_metadata")
        entry.write_text(json.dumps(cached))
        self.hosted.side_effect = AssertionError("cache miss")
        second = self.run_pipeline()
        self.assertEqual(second["calls"], 0)
        self.assertEqual(second["regions"][0]["recognition_metadata"], {})
        self.assertEqual(second["regions"][0]["candidate_text"], "לא")

    def test_ineligible_model_makes_no_inference_requests(self):
        recognize = Mock()
        check = Mock(side_effect=ocr.gateway_ocr.GatewayError("provider_not_allowed"))
        other = copy.deepcopy(self.region)
        other.update(id="two", page=2)
        self.manifest["regions"].append(other)
        report = self.run_pipeline(
            provider="vercel", gateway_recognize=recognize, gateway_check=check
        )
        self.assertEqual(report["calls"], 0)
        self.assertEqual(report["preflight_requests"], 1)
        self.assertTrue(
            all(r["error_code"] == "provider_not_allowed" for r in report["regions"])
        )
        recognize.assert_not_called()
        check.assert_called_once()

    def test_model_selection_changes_cache_and_reaches_provider(self):
        recognize = Mock(return_value={"text": "לא", "metadata": {}})
        self.run_pipeline(provider="vercel", gateway_recognize=recognize)
        result = self.run_pipeline(
            provider="vercel",
            gateway_recognize=recognize,
            gateway_model="google/gemini-3-flash",
        )
        self.assertEqual(result["calls"], 1)
        recognize.assert_called_with(b"synthetic-image", "google/gemini-3-flash")
        check = Mock(side_effect=AssertionError("cache hit must not access network"))
        cached = self.run_pipeline(
            provider="vercel",
            gateway_recognize=recognize,
            gateway_model="google/gemini-3-flash",
            gateway_check=check,
        )
        self.assertEqual(cached["preflight_requests"], 0)
        self.assertEqual(cached["calls"], 0)

    def test_gateway_error_code_is_safe_and_not_cached(self):
        recognize = Mock(side_effect=ocr.gateway_ocr.GatewayError("http_error", 401))
        report = self.run_pipeline(provider="vercel", gateway_recognize=recognize)
        item = report["regions"][0]
        self.assertEqual(item["status"], "recognition_failed")
        self.assertEqual(item["http_status"], 401)
        self.assertEqual(item["error_code"], "http_error")
        self.assertFalse((self.root / "cache").exists())

    def test_reasoning_effort_separates_cache_and_reuses_without_network(self):
        recognize = Mock(return_value={"text": "לא", "metadata": {}})
        self.run_pipeline(provider="vercel", gateway_recognize=recognize)
        check = Mock(return_value={"status": "eligible", "reasoning_effort": "low"})
        low = self.run_pipeline(
            provider="vercel",
            gateway_reasoning_effort="low",
            gateway_recognize=recognize,
            gateway_check=check,
        )
        self.assertEqual(low["calls"], 1)
        check.assert_called_once_with(ocr.gateway_ocr.MODEL, "low")
        recognize.assert_called_with(b"synthetic-image", ocr.gateway_ocr.MODEL, "low")
        forbidden = Mock(side_effect=AssertionError("cache must not access network"))
        cached = self.run_pipeline(
            provider="vercel",
            gateway_reasoning_effort="low",
            gateway_recognize=forbidden,
            gateway_check=forbidden,
        )
        self.assertEqual(cached["calls"], 0)
        self.assertEqual(cached["preflight_requests"], 0)
        high = self.run_pipeline(
            provider="vercel",
            gateway_reasoning_effort="high",
            gateway_recognize=recognize,
        )
        self.assertEqual(high["calls"], 1)

    def test_unsupported_reasoning_makes_no_inference_calls(self):
        recognize = Mock()
        check = Mock(
            side_effect=ocr.gateway_ocr.GatewayError("reasoning_effort_not_supported")
        )
        report = self.run_pipeline(
            provider="vercel",
            gateway_reasoning_effort="low",
            gateway_recognize=recognize,
            gateway_check=check,
        )
        self.assertEqual(report["calls"], 0)
        self.assertEqual(
            report["regions"][0]["error_code"], "reasoning_effort_not_supported"
        )
        recognize.assert_not_called()
        with self.assertRaisesRegex(ValueError, "requires the vercel provider"):
            self.run_pipeline(gateway_reasoning_effort="low")

    def test_rejected_gateway_response_retains_accounting_without_text_or_cache(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {
                            "content": "PRIVATE_PARTIAL",
                            "reasoning": "PRIVATE_THOUGHT",
                        },
                    }
                ],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 1024,
                    "total_tokens": 1124,
                    "completion_tokens_details": {
                        "reasoning_tokens": 1000,
                        "private": "PRIVATE_DETAIL",
                    },
                },
            }
        ).encode()
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "REPLACE_ME"}),
            patch.object(
                ocr.gateway_ocr.urllib.request, "build_opener", return_value=opener
            ),
        ):
            report = self.run_pipeline(provider="vercel")
        item = report["regions"][0]
        self.assertEqual(report["calls"], 1)
        self.assertEqual(item["status"], "recognition_failed")
        self.assertEqual(item["error_code"], "incomplete_response")
        self.assertIsNone(item["candidate_text"])
        self.assertEqual(item["raw_text"], self.region["raw_text"])
        self.assertEqual(item["recognition_metadata"]["finish_reason"], "length")
        self.assertEqual(item["recognition_metadata"]["usage"]["total_tokens"], 1124)
        self.assertEqual(
            item["recognition_metadata"]["usage"]["completion_tokens_details"],
            {"reasoning_tokens": 1000},
        )
        self.assertNotIn("PRIVATE", json.dumps(report))
        self.assertFalse((self.root / "cache").exists())
        opener.open.assert_called_once()

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


class GatewayAdapterTest(unittest.TestCase):
    def test_wire_contract_response_and_no_retries(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        data = {
            "choices": [{"finish_reason": "stop", "message": {"content": "לֹא"}}],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 3,
                "total_tokens": 103,
                "arbitrary_secret": "DO-NOT-KEEP",
            },
        }
        response.read.return_value = json.dumps(data).encode()
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "REPLACE_ME"}),
            patch.object(
                ocr.gateway_ocr.urllib.request, "build_opener", return_value=opener
            ),
        ):
            result = ocr.gateway_ocr.recognize(b"crop")
            self.assertEqual(result["text"], "לֹא")
            self.assertEqual(result["metadata"]["usage"]["total_tokens"], 103)
            self.assertNotIn("DO-NOT-KEEP", json.dumps(result))
            request = opener.open.call_args.args[0]
            body = json.loads(request.data)
            self.assertEqual(request.full_url, ocr.gateway_ocr.ENDPOINT)
            self.assertEqual(body["max_tokens"], 1024)
            self.assertNotIn("providerOptions", body)
            self.assertEqual(body["model"], ocr.gateway_ocr.MODEL)
            self.assertEqual(len(body["messages"]), 2)
            self.assertEqual(
                body["messages"][1]["content"][0]["image_url"]["url"],
                "data:image/png;base64,Y3JvcA==",
            )
            self.assertNotIn("tools", body)
            self.assertNotIn("reasoning", body)
            ocr.gateway_ocr.recognize(b"crop", reasoning_effort="low")
            low_body = json.loads(opener.open.call_args.args[0].data)
            self.assertEqual(low_body["reasoning"], {"effort": "low"})
            self.assertEqual(low_body["max_tokens"], 1024)
            self.assertEqual(
                ocr.gateway_ocr.identity()["request_sha256"],
                ocr.digest(
                    json.dumps(
                        {
                            "prompt": ocr.gateway_ocr.PROMPT,
                            "model": ocr.gateway_ocr.MODEL,
                            **ocr.gateway_ocr.SETTINGS,
                        },
                        sort_keys=True,
                    ).encode()
                ),
            )
            for failure in ("length", "tool_calls", "content_filter"):
                data["choices"][0]["finish_reason"] = failure
                response.read.return_value = json.dumps(data).encode()
                with self.assertRaises(ocr.gateway_ocr.GatewayError) as rejected:
                    ocr.gateway_ocr.recognize(b"crop")
                self.assertEqual(rejected.exception.metadata["finish_reason"], failure)
                self.assertEqual(
                    rejected.exception.metadata["usage"]["total_tokens"], 103
                )
                self.assertNotIn("DO-NOT-KEEP", json.dumps(rejected.exception.metadata))
            before = opener.open.call_count
            opener.open.side_effect = urllib.error.HTTPError(
                request.full_url, 429, "SECRET BODY", {}, None
            )
            with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                ocr.gateway_ocr.recognize(b"crop")
            self.assertEqual(error.exception.http_status, 429)
            self.assertNotIn("SECRET", str(error.exception))
            self.assertEqual(opener.open.call_count, before + 1)

    def test_rejection_metadata_sanitizes_unknown_reasons_and_invalid_counters(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "REPLACE_ME"}),
            patch.object(
                ocr.gateway_ocr.urllib.request, "build_opener", return_value=opener
            ),
        ):
            for reason in ("PRIVATE_REASON", {"private": "PRIVATE_REASON"}, None):
                with self.subTest(reason=reason):
                    response.read.return_value = json.dumps(
                        {
                            "choices": [
                                {
                                    "finish_reason": reason,
                                    "message": {"content": "PRIVATE"},
                                }
                            ],
                            "usage": {
                                "prompt_tokens": True,
                                "completion_tokens": -1,
                                "total_tokens": "100",
                                "secret": "PRIVATE",
                                "completion_tokens_details": {"reasoning_tokens": 1.5},
                                "prompt_tokens_details": {
                                    "cached_tokens": 0,
                                    "secret": "PRIVATE",
                                },
                            },
                        }
                    ).encode()
                    with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                        ocr.gateway_ocr.recognize(b"crop")
                    self.assertEqual(
                        error.exception.metadata["finish_reason"], "unknown"
                    )
                    self.assertEqual(
                        error.exception.metadata["usage"],
                        {"prompt_tokens_details": {"cached_tokens": 0}},
                    )
                    self.assertNotIn("PRIVATE", json.dumps(error.exception.metadata))

    def test_malformed_or_refused_response_keeps_safe_usage_without_accepting_it(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        cases = [
            {"choices": []},
            {"choices": [None]},
            {},
            {"choices": [{"finish_reason": "stop", "message": None}]},
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": "PRIVATE", "refusal": "PRIVATE_REFUSAL"},
                    }
                ]
            },
        ]
        with (
            patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "REPLACE_ME"}),
            patch.object(
                ocr.gateway_ocr.urllib.request, "build_opener", return_value=opener
            ),
        ):
            for data in cases:
                with self.subTest(data=data):
                    data["usage"] = {"total_tokens": 27}
                    response.read.return_value = json.dumps(data).encode()
                    with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                        ocr.gateway_ocr.recognize(b"crop")
                    self.assertEqual(
                        error.exception.metadata["usage"], {"total_tokens": 27}
                    )
                    self.assertNotIn("PRIVATE", json.dumps(error.exception.metadata))

    def test_eligibility_checks_allowlist_and_image_support(self):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        model = {
            "id": ocr.gateway_ocr.MODEL,
            "model_eligibility": {
                "status": "ineligible",
                "reason": "no_allowlisted_provider",
            },
            "modalities": {"input": ["image"], "output": ["text"]},
        }
        opener = Mock()
        opener.open.return_value = response
        with (
            patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "REPLACE_ME"}),
            patch.object(
                ocr.gateway_ocr.urllib.request, "build_opener", return_value=opener
            ),
        ):
            response.read.return_value = json.dumps({"data": [model]}).encode()
            with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                ocr.gateway_ocr.check_model(ocr.gateway_ocr.MODEL)
            self.assertEqual(error.exception.code, "provider_not_allowed")
            model["model_eligibility"] = {"status": "eligible"}
            response.read.return_value = json.dumps({"data": [model]}).encode()
            self.assertEqual(
                ocr.gateway_ocr.check_model(ocr.gateway_ocr.MODEL)["status"], "eligible"
            )
            request = opener.open.call_args.args[0]
            self.assertEqual(request.get_method(), "GET")
            self.assertIn("include_availability=true", request.full_url)
            with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                ocr.gateway_ocr.check_model(ocr.gateway_ocr.MODEL, "low")
            self.assertEqual(error.exception.code, "reasoning_effort_not_supported")
            for options in (
                [{"type": "effort", "values": ["high"]}],
                [{"type": "effort", "values": "low"}],
                [{"type": "budget_tokens", "values": ["low"]}],
            ):
                model["reasoning_options"] = options
                response.read.return_value = json.dumps({"data": [model]}).encode()
                with self.assertRaises(ocr.gateway_ocr.GatewayError):
                    ocr.gateway_ocr.check_model(ocr.gateway_ocr.MODEL, "low")
            model["reasoning_options"] = [{"type": "effort", "values": ["low", "high"]}]
            response.read.return_value = json.dumps({"data": [model]}).encode()
            self.assertEqual(
                ocr.gateway_ocr.check_model(ocr.gateway_ocr.MODEL, "low")[
                    "reasoning_effort"
                ],
                "low",
            )
            model["modalities"]["input"] = ["text"]
            response.read.return_value = json.dumps({"data": [model]}).encode()
            with self.assertRaises(ocr.gateway_ocr.GatewayError):
                ocr.gateway_ocr.check_model(ocr.gateway_ocr.MODEL)

    def test_error_type_is_retained_without_response_body(self):
        payload = json.dumps(
            {"error": {"type": "no_providers_available", "message": "PRIVATE SECRET"}}
        ).encode()
        opener = Mock()
        opener.open.side_effect = urllib.error.HTTPError(
            ocr.gateway_ocr.ENDPOINT, 403, "PRIVATE SECRET", {}, io.BytesIO(payload)
        )
        with (
            patch.dict(os.environ, {"AI_GATEWAY_API_KEY": "REPLACE_ME"}),
            patch.object(
                ocr.gateway_ocr.urllib.request, "build_opener", return_value=opener
            ),
        ):
            with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                ocr.gateway_ocr.recognize(b"crop")
            self.assertEqual(error.exception.code, "no_providers_available")
            self.assertNotIn("PRIVATE", str(error.exception))

    def test_no_key_means_no_request(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(ocr.gateway_ocr.urllib.request, "build_opener") as opener,
        ):
            with self.assertRaises(ocr.gateway_ocr.GatewayError) as error:
                ocr.gateway_ocr.recognize(b"crop")
            self.assertEqual(error.exception.code, "not_configured")
            opener.assert_not_called()

    def test_credentials_cannot_follow_redirect(self):
        self.assertIsNone(
            ocr.gateway_ocr.NoRedirect().redirect_request(
                None, None, 302, "redirect", {}, "https://other.invalid"
            )
        )


class HostedAdapterTest(unittest.TestCase):
    def test_accounting_omits_invalid_counters_and_unrecognized_models(self):
        for invalid in (None, True, False, -1, 1.5, "1", {}, []):
            with self.subTest(invalid=invalid):
                metadata = ocr.hosted_metadata(
                    {
                        "model": "PRIVATE_RESPONSE_TEXT",
                        "usage_info": {
                            "pages_processed": invalid,
                            "doc_size_bytes": 12,
                            "other": "PRIVATE",
                        },
                    }
                )
                self.assertEqual(
                    metadata,
                    {
                        "requested_model": ocr.MODEL,
                        "usage_info": {"doc_size_bytes": 12},
                    },
                )
        for missing in ({}, None, [], {"usage_info": None}, {"usage_info": []}):
            self.assertEqual(ocr.hosted_metadata(missing)["usage_info"], {})
        self.assertEqual(
            ocr.hosted_metadata(
                {
                    "model": "mistral-ocr-2503-completion",
                    "usage_info": {"pages_processed": 0, "doc_size_bytes": 0},
                }
            ),
            {
                "requested_model": ocr.MODEL,
                "reported_model": "mistral-ocr-2503-completion",
                "usage_info": {"pages_processed": 0, "doc_size_bytes": 0},
            },
        )

    def test_invalid_response_retains_only_safe_accounting(self):
        invalid_pages = (
            None,
            {},
            [],
            [None],
            [{"markdown": 42}],
            [{"markdown": " "}],
            [{"markdown": "x" * 10001}],
        )
        for pages in invalid_pages:
            with self.subTest(pages_type=type(pages).__name__):
                response = Mock()
                response.__enter__ = Mock(return_value=response)
                response.__exit__ = Mock(return_value=False)
                response.read.return_value = json.dumps(
                    {
                        "pages": pages,
                        "model": ocr.MODEL,
                        "usage_info": {"pages_processed": 1},
                        "error": "PRIVATE",
                        "document_annotation": "PRIVATE",
                    }
                ).encode()
                opener = Mock()
                opener.open.return_value = response
                with (
                    patch.dict(os.environ, {"MISTRAL_API_KEY": "test-only"}),
                    patch.object(
                        ocr.urllib.request, "build_opener", return_value=opener
                    ),
                    self.assertRaises(ocr.HostedOCRError) as error,
                ):
                    ocr.hosted_response(b"image")
                self.assertEqual(
                    error.exception.metadata["usage_info"], {"pages_processed": 1}
                )
                self.assertNotIn(
                    "PRIVATE",
                    str(error.exception) + json.dumps(error.exception.metadata),
                )
                opener.open.assert_called_once()

    def test_unparseable_and_transport_failures_have_unknown_usage(self):
        for raw in (b"not JSON PRIVATE", b"[]", b"null", b"x" * (2 * 1024 * 1024 + 1)):
            response = Mock()
            response.__enter__ = Mock(return_value=response)
            response.__exit__ = Mock(return_value=False)
            response.read.return_value = raw
            opener = Mock()
            opener.open.return_value = response
            with (
                patch.dict(os.environ, {"MISTRAL_API_KEY": "test-only"}),
                patch.object(ocr.urllib.request, "build_opener", return_value=opener),
                self.assertRaises(ocr.HostedOCRError) as error,
            ):
                ocr.hosted_response(b"image")
            self.assertFalse(error.exception.metadata.get("usage_info"))
            self.assertNotIn("PRIVATE", str(error.exception))
            opener.open.assert_called_once()

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
            self.assertEqual(error.exception.metadata, {})


class PageFrameTest(unittest.TestCase):
    PDFINFO = (
        b"Page    3 size: 612 x 792 pts (letter)\n"
        b"Page    3 rot:  0\n"
        b"Page    3 MediaBox:     0.00     0.00   612.00   828.00\n"
        b"Page    3 CropBox:      0.00    18.00   612.00   810.00\n"
        b"Page    3 BleedBox:     0.00    18.00   612.00   810.00\n"
    )

    def test_pdfinfo_boxes_parse_for_the_requested_page(self):
        with patch.object(ocr, "command", return_value=self.PDFINFO) as command:
            boxes = ocr.page_boxes(Path("source.pdf"), 3)
        self.assertEqual(boxes["media_box"], [0.0, 0.0, 612.0, 828.0])
        self.assertEqual(boxes["crop_box"], [0.0, 18.0, 612.0, 810.0])
        self.assertEqual(command.call_args.args[0][:6], ["pdfinfo", "-box", "-f", "3", "-l", "3"])

    def test_missing_boxes_are_rejected(self):
        output = b"Page    3 size: 612 x 792 pts\n"
        with patch.object(ocr, "command", return_value=output), self.assertRaises(ValueError):
            ocr.page_boxes(Path("source.pdf"), 3)

    def test_frame_flags_a_smaller_crop_box_only(self):
        same = ocr.page_frame({"media_box": [0, 0, 612, 792], "crop_box": [0, 0, 612, 792]})
        self.assertFalse(same["crop_box_differs"])
        inset = ocr.page_frame({"media_box": [0, 0, 612, 828], "crop_box": [0, 18, 612, 810]})
        self.assertTrue(inset["crop_box_differs"])
        self.assertEqual(inset["rendered_box"], "media_box")


if __name__ == "__main__":
    unittest.main()
