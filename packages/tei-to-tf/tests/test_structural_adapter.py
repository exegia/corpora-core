"""Core protocol, snapshot guards, rollback and actual Rust bridge acceptance."""

import copy
import hashlib
import os
from pathlib import Path

import pytest
from core_stub import core_report
from test_quality import AI, Checker, xml

from tei_to_tf.model import ConversionError, Source
from tei_to_tf.qa_collection import run_collection
from tei_to_tf.quality import SpellProcess, quality_convert
from tei_to_tf.structural import structural_diagnostics, structural_preview


def test_sequential_edits_keep_exact_snapshot_coordinates_and_browser_fields():
    data = "<a>😀e\u0301\r\none & two</A>".encode()
    candidate, changes = structural_preview(data, Checker(), "edition.xml")
    assert candidate == data.replace(b" & ", b" &amp; ").replace(b"</A>", b"</a>")
    assert [change["code"] for change in changes] == ["xml_bare_ampersand", "xml_tag_case"]
    snapshot = data.decode()
    for change in changes:
        assert change["source_id"] == "edition.xml"
        assert change["source_sha256"] == hashlib.sha256(snapshot.encode()).hexdigest()
        assert snapshot[change["start"] : change["end"]] == change["before"]
        assert all(isinstance(suggestion, str) for suggestion in change["suggestions"])
        assert change["core_diagnostic"]["category"] == "structural"
        snapshot = snapshot[: change["start"]] + change["after"] + snapshot[change["end"] :]
    assert snapshot.encode() == candidate


def test_partial_fix_rolls_back_and_never_exports(tmp_path):
    data = xml(body="one & two &undefined;")
    candidate, findings = structural_preview(data, Checker(), "edition.xml")
    assert candidate == data
    assert all(not issue["repairable"] for issue in findings)
    assert findings[0]["proposed_partial_fixes"][0]["after"] == "&amp;"
    report = quality_convert([], tmp_path / "out", Checker(), sources=[Source("a.xml", "a", data)])
    assert report["status"] == "blocked"
    assert report["documents"][0]["pass_2"] == []
    assert not (tmp_path / "out/corpus").exists()


@pytest.mark.parametrize("fault", ["old_bridge", "hash", "source_id", "scalar", "byte", "before"])
def test_invalid_or_stale_native_responses_fail_closed(fault):
    class BadCore:
        def structural(self, text, source_id):
            if fault == "old_bridge":
                return {"locale": "en-US", "dictionary": "en_US"}
            report = copy.deepcopy(core_report(text, source_id))
            if fault == "hash":
                report["source_sha256"] = "stale"
            elif fault == "source_id":
                report["source_id"] = "another-document"
            else:
                edit = report["diagnostics"][0]["suggestions"][0]["edits"][0]
                if fault == "before":
                    edit["before"] = "</OTHER>"
                else:
                    edit["range"]["start"][fault] += 1
            return report

    if fault == "before":
        # A non-lexical candidate is ignored and leaves the document blocked.
        candidate, findings = structural_preview(b"<a></A>", BadCore())
        assert candidate == b"<a></A>"
        assert findings[0]["blocking"]
    else:
        with pytest.raises(ConversionError, match="Invalid or stale"):
            structural_preview(b"<a></A>", BadCore())


def test_core_blocking_policy_cannot_be_bypassed_by_a_python_parse(tmp_path):
    class BlockingCore(Checker):
        def structural(self, text, source_id):
            report = core_report(text, source_id)
            report["diagnostics"] = [
                dict(
                    code="xml_node_limit",
                    message="Budget exceeded",
                    category="structural",
                    blocking=True,
                    locations=[],
                    suggestions=[],
                )
            ]
            return report

    report = quality_convert(
        [], tmp_path / "out", BlockingCore(), sources=[Source("a.xml", "a", xml())]
    )
    assert report["status"] == "blocked"
    assert any(d["code"] == "xml_node_limit" for d in report["documents"][0]["pass_3"])
    assert not (tmp_path / "out/corpus").exists()


def test_final_spelling_repair_must_pass_core_structure_again(tmp_path):
    class FinalBlockingCore(Checker):
        def structural(self, text, source_id):
            report = core_report(text, source_id)
            if "helllo" not in text:
                report["diagnostics"] = [
                    dict(
                        code="xml_node_limit",
                        message="Final budget exceeded",
                        category="structural",
                        blocking=True,
                        locations=[],
                        suggestions=[],
                    )
                ]
            return report

    report = quality_convert(
        [],
        tmp_path / "out",
        FinalBlockingCore(),
        ai=AI(),
        sources=[Source("a.xml", "a", xml(header="helllo"))],
        max_cycles=1,
    )
    row = report["documents"][0]
    assert row["status"] == "blocked"
    assert any(d["code"] == "xml_node_limit" for d in row["pass_3"])
    assert not any(change["validated"] for change in row["pass_2"])
    assert not (tmp_path / "out/corpus").exists()


def test_collection_preview_keeps_native_blockers_even_when_python_accepts_xml(tmp_path):
    class BlockingCore(Checker):
        def structural(self, text, source_id):
            report = core_report(text, source_id)
            report["diagnostics"] = [
                dict(
                    code="xml_node_limit",
                    message="Budget exceeded",
                    category="structural",
                    blocking=True,
                    locations=[],
                    suggestions=[],
                )
            ]
            return report

    validator = tmp_path / "unused-validator.py"
    validator.write_text("raise AssertionError('blocked sources must never reach validation')")
    output = tmp_path / "out"
    with pytest.raises(ConversionError, match="No documents passed source preflight"):
        run_collection(
            [Source("a.xml", "a", xml())],
            output,
            validator,
            repair_structural=True,
            structural_checker=BlockingCore(),
        )
    assert not output.exists()


@pytest.mark.skipif(not os.environ.get("CORPORA_TEXT_CHECK"), reason="Requires built Rust bridge")
def test_real_rust_structure_without_dictionaries_and_legacy_detection(tmp_path):
    checker = SpellProcess(Path(os.environ["CORPORA_TEXT_CHECK"]))
    try:
        assert checker.detect("hello world", "en-US")["dictionary"] == "en_US"
        data = "<a>😀e\u0301\r\none & two</A>".encode()
        candidate, changes = structural_preview(data, checker, "edition.xml")
        assert candidate == data.replace(b" & ", b" &amp; ").replace(b"</A>", b"</a>")
        assert [c["code"] for c in changes] == ["xml_bare_ampersand", "xml_tag_case"]
        assert structural_diagnostics(candidate, checker, "edition.xml") == []
        for data in [b"<a>one & two &unknown;</a>", b"<!DOCTYPE a><a/>"]:
            candidate, findings = structural_preview(data, checker, "edition.xml")
            assert candidate == data
            assert all(not issue["repairable"] for issue in findings)

        class NativeStructure(Checker):
            def structural(self, text, source_id):
                return checker.structural(text, source_id)

        original = xml().replace(b"</author>", b"</AUTHOR>")
        report = quality_convert(
            [],
            tmp_path / "out",
            NativeStructure(),
            sources=[Source("edition.xml", "edition", original)],
        )
        row = report["documents"][0]
        assert report["status"] == "passed"
        assert row["pass_2"][0]["core_diagnostic"]["code"] == "xml_tag_case"
        assert row["pass_2"][0]["validated"]
        assert (
            tmp_path / "out/originals" / hashlib.sha256(original).hexdigest()
        ).read_bytes() == original
    finally:
        checker.close()
