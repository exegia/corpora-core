"""Collection coverage and corruption regressions independent of public downloads."""

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest
from tf.fabric import Fabric

from tei_to_tf import ConversionError, convert
from tei_to_tf.model import Source
from tei_to_tf.qa_collection import (
    FEATURES,
    POLICY,
    navigation_page,
    oracle,
    render_reading,
    run_collection,
    verify_document,
)
from tei_to_tf.qa_quality import join_quality, marked_text, reading_issues


def test_inline_diagnostic_maps_exact_occurrence_and_preserves_text():
    from lxml import etree, html

    src = source("a.xml", "<p>😀 bad <emph>bad</emph> bad</p>")
    view = oracle(src.data)
    tree = etree.fromstring(src.data).getroottree()
    node = tree.xpath("//*[local-name()='emph']")[0]
    diagnostic = dict(
        path=tree.getpath(node),
        field="tail",
        start=1,
        end=4,
        text="bad",
        score=60,
        role="corpus",
        reason="Likely typo",
        suggestions=["good <script>"],
        blocking=True,
    )
    issues = reading_issues(src.data, view, [diagnostic])
    assert len(issues) == 1
    assert issues[0]["start"] == view["text"].rindex("bad")
    rendered = render_reading(view, issues)
    doc = html.fromstring(rendered)
    assert doc.text_content() == view["text"]
    assert len(doc.xpath('.//span[contains(@class, "qa-word")]')) == 1
    assert "<script>" not in rendered
    diagnostic["text"] = "wrong"
    assert reading_issues(src.data, view, [diagnostic]) == []


def test_inline_severity_colors_and_metadata_exclusion():
    issue = dict(start=0, end=3, score=90, reason="Metadata typo", suggestions=["good"])
    assert "qa-red" in marked_text("bad", 0, 3, [issue])
    issue["score"] = 60
    assert "qa-orange" in marked_text("bad", 0, 3, [issue])
    issue["score"] = 20
    assert "qa-yellow" in marked_text("bad", 0, 3, [issue])
    src = source("a.xml", "<p>bad</p>")
    assert reading_issues(src.data, oracle(src.data), [dict(issue, role="metadata")]) == []


def test_quality_join_requires_exact_sources_and_hashes():
    rows = [{"origin": "file:///a.xml", "sha256": "abc"}]
    receipt = {"source": "file:///a.xml", "source_sha256": "wrong", "pass_3": []}
    with pytest.raises(ConversionError, match="hash differs"):
        join_quality(rows, {"documents": [receipt]})
    assert "quality" not in rows[0]
    receipt["source_sha256"] = "abc"
    with pytest.raises(ConversionError, match="inventory differs"):
        join_quality(rows, {"documents": [receipt, receipt]})
    join_quality(rows, {"documents": [receipt]})
    assert rows[0]["quality"] == receipt


def test_quality_browser_escapes_diagnostic_payload():
    nav = navigation_page(
        [
            {
                "id": "a",
                "status": "passed",
                "quality": {
                    "pass_3": [
                        {"text": "</script><script>alert(1)", "score": 90, "suggestions": ["safe"]}
                    ]
                },
            }
        ],
        "local",
    )
    assert "</script><script>alert" not in nav
    assert 'id="quality-pass"' in nav
    assert "td.textContent=value" in nav


def source(name, content):
    xml = (
        '<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/><text><body>'
        f"<div><head>Same title</head>{content}</div></body></text></TEI>"
    )
    return Source(name, f"file:///{name}", xml.encode())


def loaded(tmp_path):
    sources = [
        source("a.xml", "<div><head>I</head><lg><l>A<emph>B</emph>C</l></lg></div>"),
        source(
            "b.xml",
            "<p>Second <choice><orig>olde</orig><reg>old</reg></choice>"
            "<note>separate</note> <app><lem>reading</lem><rdg>variant</rdg></app>.</p>",
        ),
    ]
    manifest = convert([], tmp_path / "out", sources=sources, policy=POLICY)
    api = Fabric(locations=str(tmp_path / "out/tf"), silent="deep").load(FEATURES, silent="deep")
    nodes = [manifest["graph"]["node_ids"][identity] for identity in manifest["documents"]]
    return api, nodes, [oracle(s.data) for s in sources]


def test_multiple_documents_local_offsets_and_duplicate_titles(tmp_path):
    api, nodes, views = loaded(tmp_path)
    for node, view in zip(nodes, views, strict=True):
        actual, proof = verify_document(api, node, view)
        assert render_reading(actual) == render_reading(view)
        assert proof["characters"] == len(view["text"])
    assert views[0]["title"] == views[1]["title"]
    assert "Second olde reading." in views[1]["text"]
    assert "separate" not in views[1]["text"]


def test_second_document_corruption_detected(tmp_path):
    api, nodes, views = loaded(tmp_path)
    view = copy.deepcopy(views[1])
    view["text"] += "lost"
    with pytest.raises(ConversionError, match="Document text differs"):
        verify_document(api, nodes[1], view)


def test_missing_annotation_detected_without_text_change(tmp_path):
    api, nodes, views = loaded(tmp_path)
    view = copy.deepcopy(views[0])
    view["elements"] = [e for e in view["elements"] if e["tag"] != "emph"]
    with pytest.raises(ConversionError, match="Element inventory"):
        verify_document(api, nodes[0], view)


def test_wrong_parent_detected(tmp_path, monkeypatch):
    api, nodes, views = loaded(tmp_path)
    monkeypatch.setattr(api.E.parent, "f", lambda _: (nodes[1],))
    with pytest.raises(ConversionError, match="cross-document parent"):
        verify_document(api, nodes[0], views[0])


def test_ambiguous_apparatus_is_not_silently_selected():
    with pytest.raises(ConversionError, match="Ambiguous app"):
        oracle(source("bad.xml", "<app><rdg>A</rdg></app>").data)


def test_rendering_escapes_source_and_navigation():
    view = oracle(source("a.xml", "<p>&lt;script&gt;bad&lt;/script&gt;</p>").data)
    assert "<script>" not in render_reading(view)
    nav = navigation_page(
        [{"id": "doc-1", "title": "</script><script>bad", "status": "failed", "name": "bad.xml"}],
        "local",
    )
    assert "</script><script>bad" not in nav
    assert "Choose document" in nav


@pytest.mark.skipif(not os.environ.get("TF_VALIDATOR"), reason="Requires external TF validator")
def test_collection_accounts_for_invalid_file_and_all_valid_documents(tmp_path):
    sources = [
        source("first.xml", "<p>A</p>"),
        Source("bad.xml", "file:///bad.xml", b"<broken>"),
        source("last.xml", "<p>Z</p>"),
    ]
    report = run_collection(
        sources, tmp_path / "output", Path(os.environ["TF_VALIDATOR"]) / "scripts/tf_validate.py"
    )
    assert (report["total"], report["passed"], report["failed"]) == (3, 2, 1)
    assert report["status"] == "partial"
    assert len(report["loaders"]["context-fabric-warm"]) == 2
    for row in report["documents"]:
        assert (tmp_path / "output/browser" / row["tei"]).is_file()
        assert (tmp_path / "output/browser" / row["tf"]).is_file()
    saved = json.loads((tmp_path / "output/browser/qa-report.json").read_text())
    assert saved == report


@pytest.mark.skipif(not os.environ.get("TF_VALIDATOR"), reason="Requires external TF validator")
def test_collection_retains_core_blocker_and_exports_only_other_sources(tmp_path):
    from test_quality import Checker

    class SelectiveCore(Checker):
        def structural(self, text, source_id):
            report = super().structural(text, source_id)
            if source_id.endswith("blocked.xml"):
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

    output = tmp_path / "output"
    report = run_collection(
        [source("blocked.xml", "<p>blocked</p>"), source("valid.xml", "<p>valid</p>")],
        output,
        Path(os.environ["TF_VALIDATOR"]) / "scripts/tf_validate.py",
        repair_structural=True,
        structural_checker=SelectiveCore(),
    )
    assert (report["passed"], report["failed"]) == (1, 1)
    blocked = next(row for row in report["documents"] if row["name"] == "blocked.xml")
    assert blocked["status"] == "failed"
    assert blocked["structural_diagnostics"][0]["core_diagnostic"]["code"] == "xml_node_limit"
    assert "document_id" not in blocked
    assert len(report["loaders"]["context-fabric-warm"]) == 1


@pytest.mark.skipif(not os.environ.get("TF_VALIDATOR"), reason="Requires external TF validator")
def test_repaired_xml_is_previewed_even_when_spelling_is_blocked(tmp_path):
    from test_quality import Checker

    from tei_to_tf.qa_quality import attach_quality

    original = source("case.xml", "<p>bad</P>")
    output = tmp_path / "output"
    report = run_collection(
        [original],
        output,
        Path(os.environ["TF_VALIDATOR"]) / "scripts/tf_validate.py",
        repair_structural=True,
        structural_checker=Checker(),
    )
    row = report["documents"][0]
    assert row["status"] == "passed"
    assert row["structural_repairs"][0]["after"] == "</p>"
    assert (output / "browser" / row["source"]).read_bytes() == original.data
    assert b"<p>bad</p>" in (output / "browser" / row["comparison_source"]).read_bytes()
    quality = tmp_path / "quality.json"
    quality.write_text(
        json.dumps(
            {
                "documents": [
                    {
                        "source": original.origin,
                        "source_sha256": row["sha256"],
                        "status": "blocked",
                        "pass_1": [],
                        "pass_2": row["structural_repairs"],
                        "pass_3": [],
                    }
                ]
            }
        )
    )
    attach_quality(output / "browser", quality)
    assert "Text-Fabric corrected preview" in (output / "browser" / row["tf"]).read_text()
    page = (output / "browser/index.html").read_text()
    assert "Corrected XML" in page
    assert '"status": "blocked"' in page


@pytest.mark.skipif(
    not os.environ.get("BAUDELAIRE_INVENTORY") or not os.environ.get("TF_VALIDATOR"),
    reason="Requires cached public collection inventory and external TF validator",
)
def test_pinned_complete_baudelaire_collection(tmp_path):
    inventory_path = Path(os.environ["BAUDELAIRE_INVENTORY"])
    inventory = json.loads(inventory_path.read_text())
    assert len(inventory) == 163
    sources = []
    for row in inventory:
        assert row["revision"] == "71fb49a3738a4533913327beffb39fd90633b0f1"
        data = (inventory_path.parent / row["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == row["sha256"]
        sources.append(Source(row["name"], row["origin"], data, row["revision"]))
    report = run_collection(
        sources,
        tmp_path / "collection",
        Path(os.environ["TF_VALIDATOR"]) / "scripts/tf_validate.py",
    )
    assert (report["total"], report["passed"], report["failed"]) == (163, 155, 8)
    assert report["characters"] == 247063
    assert sum(d["proof"]["lines"] for d in report["documents"] if d["status"] == "passed") == 4011
    failures = [d for d in report["documents"] if d["status"] == "failed"]
    assert sum("Malformed XML" in d["error"] for d in failures) == 7
    assert sum("Ambiguous app" in d["error"] for d in failures) == 1
