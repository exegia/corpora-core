"""Three-pass policy, provenance, and actual Matchum bridge acceptance."""

import hashlib
import os
import re
from pathlib import Path

import pytest
from core_stub import core_report

from tei_to_tf.model import Source
from tei_to_tf.parse import secure_tree
from tei_to_tf.quality import (
    SpellProcess,
    inspect_tree,
    quality_convert,
    structural_preview,
    text_segments,
)


def xml(header="hello", body="world"):
    return (
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">'
        f"<teiHeader><fileDesc><titleStmt><title>Title</title><author>{header}</author></titleStmt></fileDesc>"
        f"</teiHeader><text><body><p>{body}</p></body></text></TEI>"
    ).encode()


class Checker:
    def structural(self, text, source_id):
        return core_report(text, source_id)

    def detect(self, text, locale):
        return {"locale": locale or "en-US", "dictionary": "en_US"}

    def check(self, text, role, locale):
        diagnostics = []
        for match in re.finditer(r"helllo|archaick|unknown", text):
            word = match[0]
            score = 20 if role == "heading" else 60 if role == "corpus" else 90
            diagnostics.append(
                {
                    "code": "unknown_word",
                    "text": word,
                    "start": match.start(),
                    "end": match.end(),
                    "score": score,
                    "blocking": score == 90,
                    "replacement": "hello" if word == "helllo" and role != "corpus" else None,
                }
            )
        return {
            "language": self.detect(text, locale),
            "diagnostics": diagnostics,
            "passed": not any(d["blocking"] for d in diagnostics),
        }


class AI:
    def request(self, task, context, issues):
        return {
            "model": "test/model",
            "edits": [
                {"id": i["id"], "before": i["text"], "after": "hello", "reason": "Repeated letter"}
                for i in issues
                if task == "spelling" and i.get("text") == "helllo"
            ],
            "unresolved": [],
        }


def test_repairs_metadata_then_revalidates_before_conversion(tmp_path):
    data = xml("helllo", "archaick")
    report = quality_convert(
        [], tmp_path / "out", Checker(), ai=AI(), sources=[Source("a.xml", "file:///a.xml", data)]
    )
    row = report["documents"][0]
    assert report["status"] == "passed"
    assert row["pass_1"][0]["score"] == 90
    assert row["pass_2"][0]["after"] == "hello"
    assert all(d["score"] == 60 for d in row["pass_3"])
    assert (tmp_path / "out/originals" / hashlib.sha256(data).hexdigest()).read_bytes() == data
    assert (tmp_path / "out/corpus/tf/otype.tf").exists()


def test_corpus_typo_is_nonblocking_and_unchanged(tmp_path):
    report = quality_convert(
        [],
        tmp_path / "out",
        Checker(),
        sources=[Source("a.xml", "file:///a.xml", xml(body="helllo"))],
    )
    assert report["status"] == "passed"
    assert report["documents"][0]["pass_2"] == []
    assert (tmp_path / "out/corpus").exists()


def test_unresolved_metadata_cannot_pass(tmp_path):
    report = quality_convert(
        [],
        tmp_path / "out",
        Checker(),
        sources=[Source("a.xml", "file:///a.xml", xml(header="unknown"))],
    )
    assert report["blocked"] == 1
    assert report["documents"][0]["pass_3"][0]["blocking"]


def test_safe_xml_repairs_are_proposed_and_traceable():
    source = b"<a>one & two</A>"
    fixed, changes = structural_preview(source, Checker())
    assert fixed == b"<a>one &amp; two</a>"
    assert {d["code"] for d in changes} == {"xml_bare_ampersand", "xml_tag_case"}
    assert all(d["repairable"] for d in changes)


def test_ambiguous_xml_is_not_recovered_by_dropping_nodes():
    original = b"<a><b>text</a>"
    fixed, diagnostics = structural_preview(original, Checker())
    assert fixed == original
    assert not diagnostics[0]["repairable"]


def test_classification_keeps_note_tail_in_corpus():
    tree = secure_tree(xml(body='hello<note xml:lang="fr">note</note>world'))
    fields = [(getattr(n, f), role, lang) for n, f, role, lang in text_segments(tree)]
    assert ("note", "footnote", "fr") in fields
    assert ("world", "corpus", "en") in fields


def test_xml_fix_and_metadata_fix_share_audited_three_passes(tmp_path):
    data = xml("helllo", "world &amp; hello").replace(b"</author>", b"</AUTHOR>")
    report = quality_convert(
        [], tmp_path / "out", Checker(), ai=AI(), sources=[Source("a.xml", "file:///a.xml", data)]
    )
    assert report["status"] == "passed"
    assert len(report["documents"][0]["pass_2"]) == 2


def test_inline_words_are_checked_whole_and_not_flattened():
    tree = secure_tree(xml("hell<hi>lo</hi>"))
    issues, _ = inspect_tree(tree, Checker(), None, {})
    assert len(issues) == 1
    assert issues[0]["text"] == "helllo"
    assert not issues[0]["repairable"]
    assert issues[0]["replacement"] is None


def test_inline_text_and_tail_order_is_source_order():
    tree = secure_tree(xml(body="a<hi>b<emph>c</emph>d</hi>e"))
    actual = "".join(getattr(n, f) for n, f, role, _ in text_segments(tree) if role == "corpus")
    assert actual == "abcde"


def test_repository_and_non_tei_metadata_are_not_xml_failures(tmp_path):
    report = quality_convert(
        [],
        tmp_path / "out",
        Checker(),
        sources=[
            Source("a.xml", "file:///a.xml", xml()),
            Source("README.md", "file:///README.md", b"# Read me"),
            Source("manifest.xml", "file:///manifest.xml", b"<manifest/>"),
        ],
    )
    assert report["status"] == "passed"
    assert report["passed"] == 1
    assert report["metadata_only"] == 2


def test_explicit_toc_is_not_scored_as_corpus():
    tree = secure_tree(xml(body='<list type="toc"><item>unknown</item></list>'))
    issues, _ = inspect_tree(tree, Checker(), None, {})
    assert issues[0]["role"] == "additional"
    assert issues[0]["score"] == 90


@pytest.mark.skipif(
    not os.environ.get("CORPORA_TEXT_CHECK") or not os.environ.get("CSPELL_DICTIONARIES"),
    reason="Requires built Rust engine and installed cspell dictionaries",
)
def test_real_matchum_repair_and_revalidation(tmp_path):
    checker = SpellProcess(
        Path(os.environ["CORPORA_TEXT_CHECK"]), Path(os.environ["CSPELL_DICTIONARIES"])
    )
    try:
        report = quality_convert(
            [],
            tmp_path / "out",
            checker,
            ai=AI(),
            sources=[Source("a.xml", "file:///a.xml", xml("helllo", "hello world"))],
        )
        assert report["status"] == "passed"
        assert report["documents"][0]["pass_2"][0]["after"] == "hello"
        assert report["documents"][0]["pass_3"] == []
    finally:
        checker.close()
