import json
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from lxml import etree
from tf.fabric import Fabric

from pdf_to_tf import ConversionFailed, convert
from pdf_to_tf.cli import main
from pdf_to_tf.gate import evaluate
from pdf_to_tf.tei import TEI_NS, XML_ID, build_tei
from pdf_to_tf.verify import verify

from .helpers import PDF_BYTES, SHA, el, extraction, page, sample, write_pdf

NS = {"t": TEI_NS}
ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "crates/corpora-pdf/tests/fixtures"


def no_tools(command: list[str]):
    raise OSError("not installed in tests")


def run(tmp_path: Path, data: dict, **options):
    return convert(
        write_pdf(tmp_path), tmp_path / "out", extraction=data, runner=no_tools, **options
    )


def tree(data: dict) -> etree._Element:
    return etree.fromstring(build_tei(data, "T", {}).xml)


def by_id(root: etree._Element, ident: str) -> etree._Element:
    return root.xpath("//*[@xml:id=$i]", i=ident)[0]


# -- gate ---------------------------------------------------------------------


def test_gate_weights_pages_by_characters_and_is_strict():
    data = extraction(
        [page(1, [el("paragraph", "abcd efgh", 10)], score=1.0),
         page(2, [el("paragraph", "ab", 10)], score=0.5)]
    )  # fmt: skip
    gate = evaluate(data)
    assert gate.characters == 10
    assert gate.score == pytest.approx((8 * 1.0 + 2 * 0.5) / 10)
    assert not evaluate(extraction([page(1, [el("paragraph", "x", 1)], score=0.95)])).passed
    assert evaluate(extraction([page(1, [el("paragraph", "x", 1)], score=0.951)])).passed


def test_unscored_text_counts_as_zero_and_empty_documents_fail():
    data = extraction(
        [page(1, [el("paragraph", "aaaa", 1)], score=1.0),
         page(2, [el("paragraph", "bbbb", 1)], score=None),
         page(3, [], score=None)]
    )  # fmt: skip
    gate = evaluate(data)
    assert gate.score == pytest.approx(0.5) and not gate.passed
    assert not evaluate(extraction([page(1, [], score=None)])).passed
    with pytest.raises(ValueError):
        evaluate(data, 1.2)


# -- TEI mapping ----------------------------------------------------------------


def test_every_line_keeps_exact_text_id_and_zone():
    root = tree(sample())
    line = by_id(root, "p1e1")
    assert "".join(line.itertext()) == "First line with a link here."
    assert line.get("facs") == "#z-p1e1"
    zone = by_id(root, "z-p1e1")
    assert [zone.get(k) for k in ("ulx", "uly", "lrx", "lry")] == ["1000", "800", "3000", "920"]
    surface = by_id(root, "p1")
    assert (surface.get("n"), surface.get("lrx"), surface.get("lry")) == ("1", "9180", "11880")


def test_marks_become_nested_hi_and_ref():
    root = tree(sample())
    line = by_id(root, "p1e1")
    ref = line.find("t:ref", NS)
    assert ref.get("target") == "https://example.org/x" and ref.text == "link"
    assert line.find("t:hi", NS).get("rend") == "italic"
    head = by_id(root, "p1e0")
    assert head.get("type") == "h1" and head.find("t:hi", NS).text == "Title"


def test_crossing_and_missing_marks_are_reported_not_guessed():
    data = extraction(
        [page(1, [el("paragraph", "abcdef", 1, marks=[
            {"kind": "bold", "text": "abcd", "target": None},
            {"kind": "italic", "text": "cdef", "target": None},
            {"kind": "link", "text": "zzz", "target": "x"}])])]
    )  # fmt: skip
    built = build_tei(data, "T", {})
    assert {i.code for i in built.issues} == {"mark_overlap_dropped", "mark_not_located"}
    line = by_id(etree.fromstring(built.xml), "p1e0")
    assert "".join(line.itertext()) == "abcdef"


def test_sections_nest_by_heading_level():
    root = tree(sample())
    h2 = by_id(root, "p1e4")
    assert h2.getparent().getparent() is by_id(root, "p1e0").getparent()
    assert by_id(root, "p1e5").getparent().getparent() is h2.getparent()


def test_paragraph_lines_split_on_vertical_gap():
    root = tree(sample())
    paragraphs = root.xpath("//t:body//t:p", namespaces=NS)
    lines = [[s.get(XML_ID) for s in p.xpath("t:seg", namespaces=NS)] for p in paragraphs]
    assert lines[:2] == [["p1e1", "p1e2"], ["p1e3"]]
    assert all(s.get("type") == "line" for s in root.xpath("//t:seg", namespaces=NS))


def test_table_rows_cells_and_tab_separators():
    root = tree(sample())
    rows = root.xpath("//t:table/t:row", namespaces=NS)
    assert [[c.text for c in r] for r in rows] == [["Name", "Value"], ["Alpha", "42"]]
    assert rows[0][0].tail == "\t" and rows[0].tail == "\n"


def test_ocr_words_carry_zone_and_confidence():
    root = tree(sample())
    line = by_id(root, "p2e0")
    words = line.xpath("t:w", namespaces=NS)
    assert [w.text for w in words] == ["Ἐν", "ἀρχῇ", "ἦν"]
    assert words[1].get("cert") == "0.410" and words[1].get("facs") == "#z-p2e0w1"
    assert "".join(line.itertext()) == "Ἐν ἀρχῇ ἦν"
    assert line.get("{http://www.w3.org/XML/1998/namespace}lang") == "el"


def test_unreliable_language_is_not_declared():
    data = extraction([page(1, [el("paragraph", "x", 1)], language="eng", reliable=False)])
    line = by_id(tree(data), "p1e0")
    assert line.get("{http://www.w3.org/XML/1998/namespace}lang") is None


def test_images_whitespace_and_bad_characters():
    built = build_tei(sample(), "T", {})
    status = {m.xml_id: m.status for m in built.elements}
    assert status["p1e11"] == "omitted" and status["p1e12"] == "zero-width"
    data = extraction([page(1, [el("paragraph", "a\x0cb", 1)])])
    bad = build_tei(data, "T", {})
    assert [i.code for i in bad.issues] == ["xml_incompatible_character"]
    assert bad.elements[0].text == "a�b"


def test_words_that_do_not_join_to_line_text_are_not_split():
    data = extraction(
        [page(1, [el("paragraph", "ab cd", 1, words=[
            {"text": "ab", "bounds": el("p", "", 1)["bounds"], "confidence": 0.9}])])],
    )  # fmt: skip
    built = build_tei(data, "T", {})
    assert [i.code for i in built.issues] == ["words_text_mismatch"]
    assert not etree.fromstring(built.xml).xpath("//t:w", namespaces=NS)


def semantic_page() -> dict:
    """A journal page: running header, front matter, abstract, body and footnotes."""
    return extraction(
        [
            page(
                1,
                [
                    el("running_header", "60 Triadic to Trinitarian", 20),
                    el("title", "Triadic to", 50, h=20),
                    el("title", "Trinitarian", 72, h=20),
                    el("author", "Joshua C. Stone", 100),
                    el("affiliation", "Liberty University", 114),
                    el("h2", "Abstract", 140),
                    el("abstract", "An argument", 156),
                    el("abstract", "in two lines.", 170),
                    el("paragraph", "Body text.1", 200),
                    el("footnote", "1 A note that runs", 400, h=10),
                    el("footnote", "243 lines on.", 411, h=10),
                    el("footnote", "2 Second note.", 422, h=10),
                    el("running_footer", "62", 480),
                ],
            )
        ]
    )


def test_semantic_labels_map_to_tei_structures():
    root = tree(semantic_page())
    header = by_id(root, "p1e0")
    assert (etree.QName(header).localname, header.get("type")) == ("fw", "header")
    assert by_id(root, "p1e12").get("type") == "footer"
    title = by_id(root, "p1e1").getparent()
    assert (etree.QName(title).localname, title.get("type")) == ("ab", "title")
    assert [seg.text for seg in title] == ["Triadic to", "Trinitarian"]
    assert by_id(root, "p1e3").getparent().get("type") == "author"
    assert by_id(root, "p1e6").getparent() is by_id(root, "p1e7").getparent()
    notes = root.xpath("//t:note[@place='foot']", namespaces=NS)
    # "243" is not the next note number, so that line continues note 1.
    assert [[seg.text for seg in note] for note in notes] == [
        ["1 A note that runs", "243 lines on."],
        ["2 Second note."],
    ]


def test_numbered_paragraphs_group_lines_into_p_with_n():
    lines = [
        ("First paragraph,", 100, 1),
        ("its second line.", 113, 1),
        ("Second paragraph without a gap.", 126, 2),
    ]
    elements = []
    for text, y, number in lines:
        element = el("paragraph", text, y)
        element["paragraph"] = number
        elements.append(element)
    root = tree(extraction([page(1, elements)]))
    paragraphs = root.xpath("//t:body//t:p", namespaces=NS)
    assert [p.get("n") for p in paragraphs] == ["1", "2"]
    assert [len(p) for p in paragraphs] == [2, 1]


def bibliography() -> dict[str, Any]:
    lines = [
        ("Alston, William P. Illocutionary Acts.", 100, 1),
        ("University Press, 2000.", 113, 1),
        ("Austin, J.L. How to Do Things.", 130, 2),
    ]
    elements = [el("h2", "Bibliography", 80)]
    for text, y, number in lines:
        element = el("reference", text, y)
        element["entry"] = number
        elements.append(element)
    return extraction([page(1, elements)])


def test_bibliography_entries_group_lines_into_bibl_with_n():
    root = tree(bibliography())
    entries = root.xpath("//t:listBibl/t:bibl", namespaces=NS)
    assert [b.get("n") for b in entries] == ["1", "2"]
    assert [[seg.text for seg in b] for b in entries] == [
        ["Alston, William P. Illocutionary Acts.", "University Press, 2000."],
        ["Austin, J.L. How to Do Things."],
    ]
    # Extractions without entry numbers keep one bibl per line.
    old = bibliography()
    for element in old["pages"][0]["elements"]:
        element.pop("entry", None)
    assert len(tree(old).xpath("//t:listBibl/t:bibl", namespaces=NS)) == 3


def test_bibliography_entries_stay_in_tf_text(tmp_path):
    report = run(tmp_path, bibliography())
    assert report["verification"]["mismatches"] == 0
    tf_dir = tmp_path / "out/tei-to-tf/tf"
    api = Fabric(locations=str(tf_dir), silent="deep").load("page", silent="deep")
    text = api.T.text(next(iter(api.F.otype.s("page"))))
    assert "Illocutionary Acts.\nUniversity Press, 2000.\nAustin, J.L." in text


def test_footnotes_and_running_heads_stay_in_tf_text(tmp_path):
    report = run(tmp_path, semantic_page())
    assert report["verification"]["mismatches"] == 0
    tf_dir = tmp_path / "out/tei-to-tf/tf"
    api = Fabric(locations=str(tf_dir), silent="deep").load("page", silent="deep")
    text = api.T.text(next(iter(api.F.otype.s("page"))))
    assert text.startswith("60 Triadic to Trinitarian\n")
    assert "1 A note that runs\n243 lines on.\n2 Second note.\n" in text


# -- pipeline -------------------------------------------------------------------


def test_conversion_maps_lines_words_and_pages_into_tf(tmp_path):
    report = run(tmp_path, sample())
    assert report["status"] == "converted_with_issues"
    assert report["verification"]["mismatches"] == 0
    assert report["verification"]["checked"] == {
        "lines": 12, "words": 3, "pages": 2, "zero_width": 1, "omitted": 1,
    }  # fmt: skip
    tf_dir = tmp_path / "out/tei-to-tf/tf"
    api = Fabric(locations=str(tf_dir), silent="deep").load("page facs_surface", silent="deep")
    pages = list(api.F.otype.s("page"))
    assert [api.F.page.v(n) for n in pages] == ["1", "2"]
    assert api.T.text(pages[1]) == "Ἐν ἀρχῇ ἦν\n"
    assert "Title\nFirst line with a link here.\nsecond line.\nNew paragraph.\n" in api.T.text(
        pages[0]
    )


def test_report_locates_issues_with_tf_nodes_and_suggestions(tmp_path):
    report = run(tmp_path, sample())
    weak = next(i for i in report["issues"] if i["code"] == "low_confidence_word")
    assert (weak["page"], weak["element_index"], weak["word_index"]) == (2, 0, 1)
    assert weak["xml_id"] == "p2e0w1" and weak["tf_node"] is not None
    assert weak["text"] == "ἀρχῇ" and weak["suggestion"]
    image = next(i for i in report["issues"] if i["code"] == "visual_semantics_unverified")
    assert image["bounds"] == {"x": 100, "y": 400, "width": 300, "height": 200}
    markdown = (tmp_path / "out/conversion-report.md").read_text()
    assert "Suggested fix:" in markdown and "p2e0w1" in markdown
    assert "| Page | Method |" in markdown and "## Feature mapping" in markdown


def test_bundle_retains_source_extraction_tei_and_checksums(tmp_path):
    run(tmp_path, sample())
    out = tmp_path / "out"
    assert (out / "sources" / SHA).read_bytes() == PDF_BYTES
    assert json.loads((out / "extraction.json").read_text())["source_sha256"] == SHA
    checksums = json.loads((out / "checksums.json").read_text())
    assert {"document.tei.xml", "conversion-report.json", "tei-to-tf/manifest.json"} <= set(
        checksums
    )
    assert not list(tmp_path.glob(".out-*"))


def test_score_at_or_below_gate_writes_no_tei_or_tf(tmp_path):
    data = extraction([page(1, [el("paragraph", "text", 1)], score=0.95)])
    report = run(tmp_path, data)
    assert report["status"] == "gated"
    out = tmp_path / "out"
    assert not (out / "document.tei.xml").exists() and not (out / "tei-to-tf").exists()
    assert report["gate"]["diagnosis"]
    assert "No TEI or TF was written" in (out / "conversion-report.md").read_text()


def test_mismatched_extraction_and_existing_output_are_refused(tmp_path):
    data = sample() | {"source_sha256": "0" * 64}
    with pytest.raises(ConversionFailed, match="sha256"):
        run(tmp_path, data)
    assert not (tmp_path / "out").exists()
    (tmp_path / "out").mkdir()
    with pytest.raises(ConversionFailed, match="exists"):
        run(tmp_path, sample())


def test_verification_detects_a_wrong_mapping(tmp_path):
    run(tmp_path, sample())
    built = build_tei(sample(), "T", {})
    built.elements[1].text = "tampered"
    manifest = json.loads((tmp_path / "out/tei-to-tf/manifest.json").read_text())
    result = verify(tmp_path / "out/tei-to-tf/tf", manifest["graph"], built.elements)
    assert [i.xml_id for i in result["mismatches"]] == ["p1e1"]


# -- CLI with a fake extractor ----------------------------------------------------


def fake_extractor(tmp_path: Path, data: dict, code: int = 0) -> Path:
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps(data))
    body = tmp_path / "fake_extract.py"
    body.write_text(
        "import sys\n"
        f"sys.stdout.write(open({str(payload)!r}).read()) if {code} == 0 "
        f"else sys.stderr.write('boom')\nsys.exit({code})\n"
    )
    script = tmp_path / "fake-extract"
    script.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{body}" "$@"\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def test_cli_exit_codes(tmp_path, capsys):
    pdf = write_pdf(tmp_path)
    ok = fake_extractor(tmp_path, sample())
    assert main([str(pdf), "--output", str(tmp_path / "a"), "--extractor", str(ok)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "converted_with_issues"
    low = extraction([page(1, [el("paragraph", "text", 1)], score=0.5)])
    gated = fake_extractor(tmp_path, low)
    assert main([str(pdf), "--output", str(tmp_path / "b"), "--extractor", str(gated)]) == 3
    broken = fake_extractor(tmp_path, {}, code=2)
    assert main([str(pdf), "--output", str(tmp_path / "c"), "--extractor", str(broken)]) == 2
    assert "boom" in capsys.readouterr().err
    assert not (tmp_path / "c").exists()


# -- real extractor on the crate fixtures -------------------------------------------


def real_extractor() -> Path | None:
    path = Path(os.environ.get("PDF_EXTRACTOR", ROOT / "target/debug/corpora-pdf-extract"))
    tools = all(shutil.which(t) for t in ("pdftohtml", "pdftoppm", "pdfinfo", "tesseract"))
    return path if path.exists() and tools else None


@pytest.mark.skipif(real_extractor() is None, reason="corpora-pdf-extract or Poppler/Tesseract")
@pytest.mark.parametrize("name", ["semantic", "mixed", "scanned"])
def test_fixture_pdfs_convert_with_full_verification(tmp_path, name):
    extractor = real_extractor()
    assert extractor
    report = convert(FIXTURES / f"{name}.pdf", tmp_path / name, extractor=str(extractor))
    if name != "semantic" and report["status"] == "gated":
        # OCR confidence depends on the installed Tesseract build; gating must still explain.
        assert report["gate"]["score"] <= 0.95 and report["gate"]["diagnosis"]
        return
    assert report["status"] == "converted", report["issues"]
    assert report["gate"]["score"] > 0.95
    assert report["verification"]["mismatches"] == 0
    assert report["verification"]["checked"]["lines"] >= 11
    root = etree.parse(str(tmp_path / name / "document.tei.xml")).getroot()
    assert root.xpath("string(//t:head[@type='h1'])", namespaces=NS) == "Sample Document"
