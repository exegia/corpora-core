"""Purpose receipt binding, exclusion boundaries and actual native quality acceptance."""

import os
from pathlib import Path

import pytest
from core_stub import core_report, position
from lxml import etree
from test_quality import Checker

from tei_to_tf.model import ConversionError, Source
from tei_to_tf.parse import secure_tree
from tei_to_tf.quality import SpellProcess, inspect_tree, quality_convert


def xml(fields):
    return (
        f'<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="en">'
        f"<teiHeader><fileDesc><publicationStmt>{fields}</publicationStmt></fileDesc></teiHeader>"
        "<text><body><p>hello world</p></body></text></TEI>"
    ).encode()


class PurposeFixture(Checker):
    """Scripted core receipts; native lexical/identity policy is tested in Rust."""

    def __init__(self, blocked=False, final_block=False, fault=None):
        self.blocked = blocked
        self.final_block = final_block
        self.fault = fault
        self.requests = []
        self.language_requests = []

    def detect(self, text, locale):
        self.language_requests.append(text)
        return super().detect(text, locale)

    def purpose(self, text, source_id, expected_document_id, allow_no_namespace=False):
        self.requests.append((text, source_id, expected_document_id))
        report = core_report(text, source_id)
        report.update(
            policy_version=1,
            expected_document_id=expected_document_id,
            allow_no_namespace=allow_no_namespace,
        )
        report["fields"] = []
        tree = secure_tree(text.encode())
        cursor = 0
        for node in tree.iter():
            if not isinstance(node.tag, str) or etree.QName(node).localname not in {"date", "idno"}:
                continue
            name = etree.QName(node).localname
            start = text.index(f"<{name}", cursor)
            opening = text.index(">", start) + 1
            end = (
                opening
                if text[opening - 2 : opening] == "/>"
                else text.index(f"</{name}>", opening) + len(name) + 3
            )
            cursor = end
            value = "".join(node.itertext())
            value_end = opening + len(value)
            location = dict(start=position(text, opening), end=position(text, value_end))
            locator, current = [], node
            while current.getparent() is not None:
                parent = current.getparent()
                locator.append([n for n in parent if isinstance(n.tag, str)].index(current))
                current = parent
            blocked = name == "idno" and (
                self.blocked or self.final_block and len(self.requests) > 1
            )
            index = len(report["diagnostics"]) if blocked else None
            if blocked:
                report["diagnostics"].append(
                    dict(
                        code="tei_identifier_mismatch",
                        category="structural",
                        blocking=True,
                        message="Fixture identity inconsistency",
                        locations=[location],
                        suggestions=[
                            dict(message="Review identity policy and references", edits=[])
                        ],
                    )
                )
            report["fields"].append(
                dict(
                    element_path=list(reversed(locator)),
                    namespace=etree.QName(node).namespace or "",
                    name=name,
                    purpose="date" if name == "date" else "identifier",
                    value=value,
                    range=dict(start=position(text, start), end=position(text, end)),
                    value_ranges=[location] if value else [],
                    status="blocked" if blocked else "validated",
                    diagnostic_index=index,
                )
            )
        if self.fault == "hash":
            report["source_sha256"] = "stale"
        elif self.fault == "range":
            report["fields"][0]["value_ranges"][0]["start"]["byte"] += 1
        elif self.fault == "path":
            report["fields"][0]["element_path"].append(999)
        elif self.fault == "value":
            report["fields"][0]["value"] = "stale"
        elif self.fault == "status":
            report["fields"][0]["status"] = "blocked"
        elif self.fault == "policy":
            report["expected_document_id"] = "another-policy"
        elif self.fault == "empty":
            report["fields"] = []
        elif self.fault == "missing":
            report["fields"] = report["fields"][1:]
        return report


def test_validated_fields_bypass_language_without_joining_parent_prose():
    data = xml("<p>pre<date>2014</date>post</p><idno>doc-1</idno>")
    checker = PurposeFixture()
    issues, evidence = inspect_tree(
        secure_tree(data),
        checker,
        "en-US",
        {},
        source_xml=data,
        source_id="source",
        expected_document_id="doc-1",
    )
    assert issues == []
    assert {f["purpose"] for f in evidence["purpose_fields"]} == {"date", "identifier"}
    assert all(
        f["policy_version"] == 1 and f["expected_document_id"] == "doc-1"
        for f in evidence["purpose_fields"]
    )
    assert not any(value in {"2014", "doc-1", "prepost"} for value in checker.language_requests)
    assert "pre" in checker.language_requests and "post" in checker.language_requests
    assert all("2014" not in value and "doc-1" not in value for value in checker.language_requests)


@pytest.mark.parametrize(
    "fault", ["hash", "range", "path", "value", "status", "policy", "empty", "missing"]
)
def test_stale_or_malformed_purpose_receipts_cannot_clear_findings(fault):
    data = xml("<date>2014</date><idno>doc-1</idno>")
    with pytest.raises(ConversionError):
        inspect_tree(
            secure_tree(data),
            PurposeFixture(fault=fault),
            "en-US",
            {},
            source_xml=data,
            expected_document_id="doc-1",
        )


def test_reading_and_foreign_fields_do_not_require_a_purpose_receipt():
    data = xml('<x:date xmlns:x="urn:other">metadata</x:date>').replace(
        b"hello world", b"hello <date>2014</date> world"
    )
    _, evidence = inspect_tree(secure_tree(data), Checker(), "en-US", {}, source_xml=data)
    assert evidence["purpose_fields"] == []


@pytest.mark.parametrize(
    "content",
    [
        '<p>pre<date when="2014"/>post</p>',
        '<p>pre<date when="2014"/><hi>post</hi></p>',
    ],
)
def test_empty_structured_elements_preserve_prose_boundaries(content):
    data = xml(content)
    checker = PurposeFixture()
    inspect_tree(secure_tree(data), checker, "en-US", {}, source_xml=data)
    assert "pre" in checker.language_requests and "post" in checker.language_requests
    assert "prepost" not in checker.language_requests


def test_purpose_blockers_survive_ai_corrections_and_both_passes(tmp_path):
    class NoSpellingAI:
        def request(self, *args):
            raise AssertionError("Typed metadata must not be sent to spelling AI")

    checker = PurposeFixture(blocked=True)
    data = xml("<date>2014</date><idno>doc-2</idno>")
    report = quality_convert(
        [],
        tmp_path / "out",
        checker,
        locale="en-US",
        metadata_locale="en-US",
        corrections={"doc-2": "doc-1"},
        ai=NoSpellingAI(),
        max_cycles=1,
        sources=[Source("doc-1.xml", "source", data)],
    )
    row = report["documents"][0]
    assert row["status"] == "blocked"
    assert row["pass_1"][0]["validation_kind"] == "purpose"
    assert row["pass_3"][0]["code"] == "tei_identifier_mismatch"
    assert row["pass_3"][0]["core_diagnostic"]["locations"]
    assert row["pass_3"][0]["purpose_policy"]["expected_document_id"] == "doc-1"
    assert row["pass_2"] == []
    assert not (tmp_path / "out/corpus").exists()
    assert len(checker.requests) == 2
    assert {r[2] for r in checker.requests} == {"doc-1"}


def test_final_purpose_revalidation_can_block_a_previously_valid_field(tmp_path):
    checker = PurposeFixture(final_block=True)
    report = quality_convert(
        [],
        tmp_path / "out",
        checker,
        max_cycles=1,
        sources=[Source("doc-1.xml", "source", xml("<idno>doc-1</idno>"))],
    )
    assert report["status"] == "blocked"
    assert report["documents"][0]["pass_3"][0]["code"] == "tei_identifier_mismatch"
    assert not (tmp_path / "out/corpus").exists()


@pytest.mark.skipif(
    not os.environ.get("CORPORA_TEXT_CHECK") or not os.environ.get("CSPELL_DICTIONARIES"),
    reason="Requires native purpose engine and dictionaries",
)
@pytest.mark.parametrize(
    "identifier,passed", [("doc-1", True), ("doc-2", False), ("doc-1-", False)]
)
def test_real_engine_validates_structured_values_and_blocks_id_mismatches(
    tmp_path, identifier, passed
):
    checker = SpellProcess(
        Path(os.environ["CORPORA_TEXT_CHECK"]), Path(os.environ["CSPELL_DICTIONARIES"])
    )
    data = xml(f"<date when='2000-02-29'>2000</date><idno>{identifier}</idno>")
    try:
        report = quality_convert(
            [],
            tmp_path / "out",
            checker,
            locale="en-US",
            max_cycles=1,
            sources=[Source("doc-1.xml", "source", data)],
        )
    finally:
        checker.close()
    row = report["documents"][0]
    assert (row["status"] == "passed") == passed
    assert [f["status"] for f in row["language"]["purpose_fields"]] == [
        "validated",
        "validated" if passed else "blocked",
    ]
    assert not any(d["code"] == "language_unresolved" for d in row["pass_3"])
    if not passed:
        assert row["pass_3"][0]["code"] == "tei_identifier_mismatch"
        location = row["pass_3"][0]["core_diagnostic"]["locations"][0]
        assert data[location["start"]["byte"] : location["end"]["byte"]].decode() == identifier
    assert (tmp_path / "out" / row["repaired_file"]).read_bytes() == data
