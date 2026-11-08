"""AI proposals are untrusted; scores, local checks and provenance remain authoritative."""

import hashlib
import json

import pytest
from test_quality import AI, Checker, xml

from tei_to_tf.hosted_ai import HostedAI, structural_proposal
from tei_to_tf.model import ConversionError, Source
from tei_to_tf.qa_quality import marked_text, repaired_sources
from tei_to_tf.quality import quality_convert


def test_red_requires_ai_but_orange_and_yellow_do_not_block(tmp_path):
    data = xml("unknown", "helllo <head>unknown</head> Unknown")
    report = quality_convert([], tmp_path / "out", Checker(), sources=[Source("a.xml", "a", data)])
    row = report["documents"][0]
    assert row["status"] == "blocked"
    assert {d["score"] for d in row["pass_1"]} == {20, 60, 90}
    assert all(d["blocking"] == (d["score"] == 90) for d in row["pass_1"])
    assert row["pass_2"] == []
    assert "No validated progress" in row["stop_reason"]


def test_ai_orange_suggestion_does_not_change_corpus(tmp_path):
    report = quality_convert(
        [], tmp_path / "out", Checker(), ai=AI(), sources=[Source("a.xml", "a", xml(body="helllo"))]
    )
    row = report["documents"][0]
    assert row["status"] == "passed"
    assert row["pass_3"][0]["ai_suggestion"] == "hello"
    assert row["pass_2"] == []
    assert b"helllo" in (tmp_path / "out" / row["repaired_file"]).read_bytes()


class XMLAI:
    def request(self, task, context, issues):
        before = "</wrong>"
        return {
            "model": "test/model",
            "edits": [
                dict(
                    id=context.index(before), before=before, after="</author>", reason="Closing tag"
                )
            ]
            if task == "xml" and before in context
            else [],
            "unresolved": [],
        }


def test_ai_closing_tag_fix_preserves_original_and_revalidates(tmp_path):
    data = xml().replace(b"</author>", b"</wrong>")
    report = quality_convert(
        [], tmp_path / "out", Checker(), ai=XMLAI(), sources=[Source("a.xml", "a", data)]
    )
    row = report["documents"][0]
    assert row["status"] == "passed"
    assert row["pass_1"][0]["ai_status"] == "reviewed"
    assert row["pass_2"][0]["code"] == "ai_xml_repair"
    assert row["pass_3"] == []
    assert (tmp_path / "out/originals" / hashlib.sha256(data).hexdigest()).read_bytes() == data


@pytest.mark.parametrize("before,after", [("word", "rewritten"), ("</x>", ""), ("<a>", "<b>")])
def test_ai_cannot_rewrite_corpus_or_delete_markup(before, after):
    class BadAI:
        def request(self, *args):
            return {"edits": [dict(id=0, before=before, after=after, reason="bad")]}

    data = before.encode()
    assert structural_proposal(data, [], BadAI()) == (data, [])


def test_bridge_budget_stops_before_subprocess(tmp_path):
    bridge = tmp_path / "bridge.mjs"
    bridge.write_text("process.stdout.write(JSON.stringify({edits:[],unresolved:[]}))")
    ai = HostedAI(bridge, "test/model", 1)
    assert ai.request("xml", "a", [])["edits"] == []
    assert ai.request("xml", "a", [])["edits"] == []  # Identical request is cached.
    assert ai.request("xml", "b", [])["error"] == "request_budget_exhausted"


def test_prepared_copy_requires_hash_and_confined_path(tmp_path):
    original = Source("a.xml", "a", xml())
    receipt = dict(
        source="a",
        source_sha256=hashlib.sha256(original.data).hexdigest(),
        repaired_file="fixed.xml",
        repaired_sha256="wrong",
        pass_2=[],
    )
    report = tmp_path / "quality.json"
    (tmp_path / "fixed.xml").write_bytes(xml(body="changed"))
    report.write_text(json.dumps({"documents": [receipt]}))
    with pytest.raises(ConversionError, match="hash differs"):
        repaired_sources([original], report)
    receipt["repaired_file"] = "../outside.xml"
    report.write_text(json.dumps({"documents": [receipt]}))
    with pytest.raises(ConversionError, match="escapes"):
        repaired_sources([original], report)


def test_ai_tooltip_escapes_suggestion_without_native_tooltip():
    rendered = marked_text(
        "bad",
        0,
        3,
        [dict(start=0, end=3, score=60, ai_suggestion='<script>"', ai_status="reviewed")],
    )
    assert "AI: &lt;script&gt;&quot;" in rendered
    assert "title=" not in rendered
    assert "qa-orange" in rendered


def test_structural_retry_retains_failed_cycle_and_only_exports_valid_result(tmp_path):
    class RetryAI:
        def request(self, task, context, issues):
            before = "</wrong>" if "</wrong>" in context else "</other>"
            if task != "xml" or before not in context:
                return {"edits": []}
            after = "</other>" if before == "</wrong>" else "</author>"
            return {
                "edits": [
                    dict(id=context.index(before), before=before, after=after, reason="Closing tag")
                ],
                "model": "test/model",
            }

    data = xml().replace(b"</author>", b"</wrong>")
    report = quality_convert(
        [], tmp_path / "out", Checker(), ai=RetryAI(), sources=[Source("a.xml", "a", data)]
    )
    row = report["documents"][0]
    assert row["status"] == "passed"
    assert len(row["cycles"]) == 2
    assert row["cycles"][0]["pass_3"][0]["blocking"]
    assert row["pass_3"] == []
    assert (tmp_path / "out/corpus/tf/otype.tf").exists()


@pytest.mark.parametrize("replacement", [" ", "!!!", "123"])
def test_ai_cannot_remove_a_metadata_word(tmp_path, replacement):
    class DeleteAI:
        def request(self, task, context, issues):
            return {
                "edits": [
                    dict(id=i["id"], before=i["text"], after=replacement, reason="bad")
                    for i in issues
                ]
            }

    report = quality_convert(
        [],
        tmp_path / "out",
        Checker(),
        ai=DeleteAI(),
        sources=[Source("a.xml", "a", xml("unknown"))],
    )
    assert report["blocked"] == 1
    assert report["documents"][0]["pass_2"] == []


def test_unvalidated_last_cycle_proposal_is_not_reported_as_repaired(tmp_path):
    class WrongAI:
        def request(self, task, context, issues):
            before = "</wrong>" if "</wrong>" in context else "</other>"
            return {
                "edits": [
                    dict(
                        id=context.index(before),
                        before=before,
                        after="</other>",
                        reason="Still wrong",
                    )
                ]
            }

    report = quality_convert(
        [],
        tmp_path / "out",
        Checker(),
        ai=WrongAI(),
        max_cycles=1,
        sources=[Source("a.xml", "a", xml().replace(b"</author>", b"</wrong>"))],
    )
    row = report["documents"][0]
    assert row["status"] == "blocked"
    assert all(d["validated"] is False for d in row["pass_2"])
    assert "repaired_file" not in row
    assert not (tmp_path / "out/corpus").exists()


def test_metadata_only_document_keeps_initial_diagnostics(tmp_path):
    report = quality_convert(
        [], tmp_path / "out", Checker(), sources=[Source("a.xml", "a", b"<manifest></MANIFEST>")]
    )
    row = report["documents"][0]
    assert row["status"] == "metadata-only"
    assert row["pass_1"]
    assert row["pass_2"]
