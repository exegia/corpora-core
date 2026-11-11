"""Opt-in page milestones and facsimile zone features."""

import json

import pytest
from tf.fabric import Fabric

from tei_to_tf import ConversionError, Policy, convert
from tei_to_tf.model import Source

NS = "http://www.tei-c.org/ns/1.0"
XMLNS = "http://www.w3.org/XML/1998/namespace"

FACSIMILE = (
    '<facsimile><surface xml:id="s1" n="1" ulx="0" uly="0" lrx="6120" lry="7920">'
    '<zone xml:id="z1" ulx="10" uly="20" lrx="300" lry="60"/></surface>'
    '<surface xml:id="s2" n="2" ulx="0" uly="0" lrx="6120" lry="7920">'
    '<zone xml:id="z2" ulx="11" uly="21" lrx="301" lry="61"/></surface></facsimile>'
)


def tei(body: str, facsimile: str = FACSIMILE) -> bytes:
    return (
        f'<TEI xmlns="{NS}"><teiHeader/>{facsimile}<text><body>{body}</body></text></TEI>'
    ).encode()


def run(tmp_path, data, policy):
    output = tmp_path / "out"
    manifest = convert([], output, policy, sources=[Source("t.xml", "file:///fixed/t.xml", data)])
    wanted = "text page tei_tag facs_surface facs_ulx facs_uly facs_lrx facs_lry".split()
    present = [name for name in wanted if (output / "tf" / f"{name}.tf").exists()]
    api = Fabric(locations=str(output / "tf"), silent="deep").load(" ".join(present), silent="deep")
    assert api
    return manifest, api


BODY = (
    '<pb n="1" facs="#s1"/><div><head facs="#z1">Title</head>\n<p>One.</p></div>'
    '<pb n="2" facs="#s2"/><div><p facs="#z2">Two.</p></div>'
)


def test_default_policy_keeps_milestones_as_offsets(tmp_path):
    manifest, api = run(tmp_path, tei(BODY), Policy())
    assert "pages" not in manifest["graph"]
    assert not list(api.F.otype.s("page"))
    assert not (tmp_path / "out" / "tf" / "facs_ulx.tf").exists()


def test_pages_span_from_pb_to_next_pb_across_divisions(tmp_path):
    manifest, api = run(tmp_path, tei(BODY), Policy(milestones="pages", facsimile="zones"))
    pages = list(api.F.otype.s("page"))
    assert [api.F.page.v(n) for n in pages] == ["1", "2"]
    assert [api.T.text(n) for n in pages] == ["Title\nOne.", "Two."]
    assert manifest["graph"]["pages"] == {
        "count": 2,
        "empty": [],
        "characters_outside_pages": 0,
    }
    assert [api.F.facs_surface.v(n) for n in pages] == ["1", "2"]
    assert api.F.facs_lry.v(pages[0]) == 7920


def test_zone_features_are_integers_on_elements(tmp_path):
    _, api = run(tmp_path, tei(BODY), Policy(milestones="pages", facsimile="zones"))
    head = next(n for n in api.F.otype.s("element") if api.F.tei_tag.v(n) == "head")
    assert (api.F.facs_ulx.v(head), api.F.facs_uly.v(head)) == (10, 20)
    assert (api.F.facs_lrx.v(head), api.F.facs_lry.v(head)) == (300, 60)
    assert api.F.facs_surface.v(head) == "1"


def test_text_before_first_pb_and_empty_pages_are_reported(tmp_path):
    body = '<p>Lead.</p><pb n="1"/><pb n="2"/><p>After.</p>'
    manifest, api = run(tmp_path, tei(body, ""), Policy(milestones="pages"))
    pages = manifest["graph"]["pages"]
    assert pages["count"] == 1
    assert pages["characters_outside_pages"] == len("Lead.")
    assert [x["n"] for x in pages["empty"]] == ["1"]
    assert [api.T.text(n) for n in api.F.otype.s("page")] == ["After."]


def test_unresolved_facs_is_listed_not_guessed(tmp_path):
    body = '<pb n="1"/><p facs="#missing">Text.</p>'
    manifest, _ = run(tmp_path, tei(body), Policy(milestones="pages", facsimile="zones"))
    unresolved = [x for x in manifest["graph"]["unresolved_references"] if x["attribute"] == "facs"]
    assert [x["reference"] for x in unresolved] == ["#missing"]


def test_non_integer_zone_coordinates_are_rejected(tmp_path):
    facsimile = FACSIMILE.replace('ulx="10"', 'ulx="10.5"')
    with pytest.raises(ConversionError, match="not an integer"):
        run(tmp_path, tei(BODY, facsimile), Policy(milestones="pages", facsimile="zones"))
    assert not (tmp_path / "out").exists()


def test_zone_table_is_retained_in_document_json(tmp_path):
    manifest, _ = run(tmp_path, tei(BODY), Policy(facsimile="zones"))
    document = manifest["documents"][0]
    data = json.loads((tmp_path / "out" / "documents" / f"{document}.json").read_text())
    assert data["metadata"]["facsimile_zones"]["z2"] == {
        "surface": "2",
        "ulx": "11",
        "uly": "21",
        "lrx": "301",
        "lry": "61",
    }


def test_policy_rejects_unknown_modes():
    with pytest.raises(ConversionError):
        Policy(milestones="lines")
    with pytest.raises(ConversionError):
        Policy(facsimile="boxes")
