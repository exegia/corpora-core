import datetime
import hashlib
import json
from pathlib import Path

import pytest
from cfabric.core import Fabric as CF
from tf.fabric import Fabric

from tei_to_tf import ConversionError, Policy, convert
from tei_to_tf.model import Source
from tei_to_tf.parse import parse

NS = "http://www.tei-c.org/ns/1.0"


def tei(body, header="", front="", back=""):
    return (
        f'<TEI xmlns="{NS}"><teiHeader>{header}</teiHeader><text>'
        f"{front}<body>{body}</body>{back}</text></TEI>"
    ).encode()


def source(data, name="test.xml"):
    return Source(name, "file:///fixed/" + name, data)


def doc(data, policy=None):
    return parse(source(data), policy or Policy())[0][0]


def test_metadata_and_toc_are_not_corpus_text():
    data = tei(
        '<div type="chapter" n="1"><head>Heading</head><p>Author is in the story.'
        '<persName ref="https://example.org/person">Ada</persName>!</p></div>',
        "<fileDesc><titleStmt><title>Work</title><author>Writer</author></titleStmt>"
        "<publicationStmt><publisher>Press</publisher></publicationStmt>"
        "<sourceDesc><bibl><title>Other title</title><author>Other author</author>"
        "</bibl></sourceDesc></fileDesc>",
        "<front><titlePage><docTitle>Printed title</docTitle></titlePage>"
        '<div type="toc"><head>Contents</head><list><item>Heading</item></list></div>'
        '<div type="preface"><p>Preface.</p></div></front>',
        '<back><div type="appendix"><p>Appendix.</p></div></back>',
    )
    result = doc(data)
    assert result.metadata["titles"] == ["Work"]
    assert result.metadata["authors"] == ["Writer"]
    assert result.metadata["publishers"] == ["Press"]
    assert result.text == "Preface.HeadingAuthor is in the story.Ada!Appendix."
    assert {x["reason"] for x in result.excluded} == {
        "document-metadata",
        "explicit-table-of-contents",
    }
    assert result.outline[1]["headings"] == ["Heading"]


def test_exact_mixed_content_unicode_and_empty_milestones():
    result = doc(tei('<p xml:space="preserve"> A<hi>é😀</hi>\tB<lb/> C&amp;D\n</p>'))
    assert result.text == " Aé😀\tB C&D\n"
    hi = next(x for x in result.elements if x.tag == "hi")
    assert result.text[hi.start : hi.end] == "é😀"
    lb = next(x for x in result.elements if x.tag == "lb")
    assert lb.start == lb.end == 7
    assert any(x["tag"] == "lb" for x in result.diagnostics)


@pytest.mark.parametrize(
    "choice,apparatus,witness,expected",
    [
        ("original", "lemma", None, "AoldlemmaZ"),
        ("edited", "witness", "#A", "AnewvariantZ"),
    ],
)
def test_editorial_selection(choice, apparatus, witness, expected):
    data = tei(
        "<p>A<choice><orig>old</orig><reg>new</reg></choice>"
        '<app><lem>lemma</lem><rdg wit="#A #B">variant</rdg></app>Z</p>'
    )
    result = doc(data, Policy(choice, apparatus, witness))
    assert result.text == expected
    assert len(result.excluded) == 2


@pytest.mark.parametrize(
    "body,policy,error",
    [
        ("<p><choice><orig>A</orig><reg>B</reg></choice></p>", Policy(), "choice needs"),
        ("<p><app><lem>A</lem></app></p>", Policy(), "app needs"),
        (
            '<p><app><rdg wit="#AA">A</rdg></app></p>',
            Policy(apparatus="witness", witness="#A"),
            "exactly one",
        ),
        (
            '<p><app><rdg wit="#A">A</rdg><rdg wit="#A">B</rdg></app></p>',
            Policy(apparatus="witness", witness="#A"),
            "exactly one",
        ),
        ('<p><hi copyOf="#a"/></p>', Policy(), "copyOf"),
        ('<p><anchor spanTo="#a"/></p>', Policy(), "spanTo"),
        (
            "<p><choice><orig>A</orig>text<reg>B</reg></choice></p>",
            Policy(choice="edited"),
            "Ambiguous text",
        ),
    ],
)
def test_ambiguity_is_not_silently_flattened(body, policy, error):
    with pytest.raises(ConversionError, match=error):
        doc(tei(body), policy)


def test_notes_are_explicit_and_tail_is_preserved():
    data = tei("<p>A<note>Comment</note>B</p>")
    assert doc(data).text == "AB"
    assert doc(data, Policy(notes="include")).text == "ACommentB"


def test_grouped_documents_and_collection_headers():
    data = (
        f'<teiCorpus xmlns="{NS}"><teiHeader><fileDesc><titleStmt>'
        "<title>Collection</title></titleStmt></fileDesc></teiHeader>"
        "<TEI><teiHeader/><text><group><text><body><p>A</p></body></text>"
        "<text><body><p>B</p></body></text></group></text></TEI>"
        "<TEI><teiHeader/><text><body><p>C</p></body></text></TEI></teiCorpus>"
    ).encode()
    docs, info = parse(source(data), Policy())
    assert [d.text for d in docs] == ["A", "B", "C"]
    assert len({d.id for d in docs}) == 3
    assert info["collection_metadata"][0]["titles"] == ["Collection"]
    assert docs[0].metadata["collection_headers"][0]["titles"] == ["Collection"]


def test_no_namespace_requires_opt_in():
    data = b"<TEI><text><body><p>Text</p></body></text></TEI>"
    with pytest.raises(ConversionError, match="namespace"):
        doc(data)
    assert doc(data, Policy(allow_no_namespace=True)).text == "Text"


@pytest.mark.parametrize(
    "data,error",
    [
        (b'<!DOCTYPE TEI [<!ENTITY x "expanded">]><TEI/>', "DTD"),
        (tei('<p xml:id="a">A</p><p xml:id="a">B</p>'), "ID a already defined"),
        (tei('<xi:include xmlns:xi="http://www.w3.org/2001/XInclude" href="a.xml"/>'), "XInclude"),
        (f'<TEI xmlns="{NS}"><sourceDoc/></TEI>'.encode(), "sourceDoc"),
        (f'<TEI xmlns="{NS}"><standOff><spanGrp/></standOff></TEI>'.encode(), "standOff"),
    ],
)
def test_unsafe_or_unsupported_xml_is_rejected(data, error):
    with pytest.raises(ConversionError, match=error):
        doc(data)


def test_conversion_determinism_loaders_and_provenance(tmp_path, monkeypatch):
    data = tei(
        '<div><head>Title</head><p xml:id="p1"> A<hi rend="italic">é😀</hi>'
        '<ref target="#p1">link</ref><lb/> Z</p></div>'
    )
    src = source(data)
    outputs = [tmp_path / "one", tmp_path / "two"]
    manifests = []
    for day, out in enumerate(outputs, 1):
        monkeypatch.setattr(
            "tf.core.data.utcnow",
            lambda day=day: datetime.datetime(2026, 1, day, tzinfo=datetime.UTC),
        )
        manifests.append(convert([], out, sources=[src]))
    assert manifests[0] == manifests[1]
    assert (outputs[0] / "checksums.json").read_bytes() == (
        outputs[1] / "checksums.json"
    ).read_bytes()
    assert (outputs[0] / "sources" / hashlib.sha256(data).hexdigest()).read_bytes() == data
    document = json.loads(next((outputs[0] / "documents").glob("*.json")).read_text())
    assert document["text"] == "Title Aé😀link Z"
    number = manifests[0]["graph"]["node_ids"][document["id"]]
    for factory in (Fabric, CF):
        for _ in range(2):
            api = factory(locations=str(outputs[0] / "tf"), silent="deep").load(
                "text document region block tei_tag start end parent link_target", silent="deep"
            )
            assert api is not False
            assert api.T.text(number) == document["text"]
            for n in api.F.otype.s("block"):
                section = api.T.sectionFromNode(n)
                assert api.T.nodeFromSection(section) == n
            hi = next(n for n in api.F.otype.s("element") if api.F.tei_tag.v(n) == "hi")
            assert api.T.text(hi) == "é😀"
            assert len(api.E.parent.f(hi)) == 1
            ref = next(n for n in api.F.otype.s("element") if api.F.tei_tag.v(n) == "ref")
            assert len(api.E.link_target.f(ref)) == 1
    with pytest.raises(ConversionError, match="already exists"):
        convert([], outputs[0], sources=[src])


def test_manifest_and_schema_files_are_separate(tmp_path):
    sources = [
        source(tei("<p>Only text</p>")),
        source(b'{"author":"Metadata"}', "manifest.json"),
        source(b"<manifest><title>Metadata</title></manifest>", "manifest.xml"),
    ]
    out = tmp_path / "out"
    result = convert([], out, sources=sources)
    assert len(result["documents"]) == 1
    assert [s["classification"] for s in result["sources"]] == [
        "tei",
        "repository-metadata",
        "non-tei-metadata",
    ]
    assert next((out / "documents").glob("*.txt")).read_text() == "Only text"


def test_failure_leaves_no_partial_output(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ConversionError):
        convert([], out, sources=[source(tei("<p>Good</p>")), source(b"<TEI>", "bad.xml")])
    assert not out.exists()


def test_metadata_only_refused(tmp_path):
    with pytest.raises(ConversionError, match="No TEI reading content"):
        convert(
            [], tmp_path / "out", sources=[source(f'<TEI xmlns="{NS}"><teiHeader/></TEI>'.encode())]
        )


def test_schema_validation_is_explicit(tmp_path):
    schema = tmp_path / "test.rng"
    schema.write_text(
        f'<element xmlns="http://relaxng.org/ns/structure/1.0" name="TEI" ns="{NS}">'
        "<empty/></element>"
    )
    with pytest.raises(ConversionError, match="Schema validation failed"):
        convert([], tmp_path / "out", schema=schema, sources=[source(tei("<p>A</p>"))])


def test_editorial_headings_use_selected_text():
    result = doc(
        tei("<div><head><choice><orig>Old</orig><reg>New</reg></choice></head><p>Body</p></div>"),
        Policy(choice="edited"),
    )
    assert result.outline[0]["headings"] == ["New"]


def test_foreign_choice_branches_rejected():
    with pytest.raises(ConversionError, match="Foreign choice"):
        doc(
            tei(
                '<p><choice><orig xmlns="urn:foreign">A</orig>'
                '<reg xmlns="urn:foreign">B</reg></choice></p>'
            ),
            Policy(choice="edited"),
        )


@pytest.mark.parametrize(
    "markup", ["<subst><del>old</del><add>new</add></subst>", "<del>old</del>", "<add>new</add>"]
)
def test_transcription_requires_supported_policy(markup):
    with pytest.raises(ConversionError, match="transcription"):
        doc(tei(f"<p>{markup}</p>"))


def test_group_interstitial_text_not_dropped():
    data = (
        f'<TEI xmlns="{NS}"><text>LOST<group><text><body><p>kept</p>'
        "</body></text></group>LOST2</text></TEI>"
    ).encode()
    with pytest.raises(ConversionError, match="outside grouped"):
        doc(data)


def test_markdown_html_is_repository_metadata(tmp_path):
    result = convert(
        [],
        tmp_path / "out",
        sources=[
            source(tei("<p>Text</p>")),
            source(b'<img src="logo.png">\n# Readme', "README.md"),
        ],
    )
    assert result["sources"][1]["classification"] == "repository-metadata"


def test_graph_limits_cleanup_reserved_output(tmp_path):
    out = tmp_path / "out"
    with pytest.raises(ConversionError, match="slot/membership"):
        convert([], out, Policy(max_memberships=2), sources=[source(tei("<p>ABC</p>"))])
    assert not out.exists()
    assert not list(tmp_path.iterdir())
    with pytest.raises(ConversionError, match="max_slots"):
        doc(tei("<p>ABC</p>"), Policy(max_slots=2))


def test_cli_enforces_policy_and_limits(tmp_path, capsys):
    from tei_to_tf.cli import main

    fixture = Path(__file__).parent / "fixtures/edition.tei.xml"
    assert main([str(fixture), "--output", str(tmp_path / "limited"), "--max-slots", "1"]) == 2
    assert "max_slots" in capsys.readouterr().err
    assert main([str(fixture), "--output", str(tmp_path / "good")]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "converted"


def test_whitespace_only_member_does_not_become_corpus(tmp_path):
    data = (
        f'<teiCorpus xmlns="{NS}"><TEI><text><body> \n </body></text></TEI>'
        "<TEI><text><body><p>Real</p></body></text></TEI></teiCorpus>"
    ).encode()
    result = convert([], tmp_path / "out", sources=[source(data)])
    assert result["graph"]["max_slot"] == 4
    assert len(result["metadata_only_documents"]) == 1
    assert result["metadata_only_documents"][0] not in result["graph"]["node_ids"]


def test_every_projected_element_matches_explicit_source_ranges(tmp_path):
    data = tei("<p>A<hi>B<seg>C</seg>D</hi>E</p>")
    result = convert([], tmp_path / "out", sources=[source(data)])
    document = json.loads(next((tmp_path / "out/documents").glob("*.json")).read_text())
    expected = {"body": "ABCDE", "p": "ABCDE", "hi": "BCD", "seg": "C"}
    for factory in (Fabric, CF):
        api = factory(locations=str(tmp_path / "out/tf"), silent="deep").load(
            "text tei_tag start end", silent="deep"
        )
        for element in document["elements"]:
            number = result["graph"]["node_ids"][document["id"] + ":" + element["key"]]
            assert api.T.text(number) == expected[element["tag"]]
            assert (
                document["text"][api.F.start.v(number) : api.F.end.v(number)]
                == expected[element["tag"]]
            )
