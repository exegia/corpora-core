"""Independent reading expectations and loader acceptance for a tiny EPUB."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from cfabric import Fabric as ContextFabric
from tf.fabric import Fabric

from epub_to_tf import ConversionError, convert

ROOT = Path(__file__).resolve().parents[3]
CHECKER = ROOT / "target/debug/corpora-epub-check"
CONTAINER = b"""<?xml version="1.0"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
<rootfiles><rootfile full-path="OEBPS/book.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>"""
OPF = b"""<?xml version="1.0"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="pub-id">urn:isbn:9780000000001</dc:identifier><dc:title>Nav only title</dc:title></metadata>
<manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest>
<spine><itemref idref="chapter"/></spine></package>"""
CHAPTER = """<html xmlns="http://www.w3.org/1999/xhtml"><head><title>Head only</title></head><body><section><h1>Á<em>β</em></h1><p>café &amp; 東京</p></section></body></html>""".encode()
NAV = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><nav>NOT READING</nav></body></html>'


def fixture(
    path: Path, *, opf: bytes = OPF, chapter: bytes = CHAPTER, extra: dict[str, bytes] | None = None
) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        files = {
            "OEBPS/": b"",
            "META-INF/container.xml": CONTAINER,
            "OEBPS/book.opf": opf,
            "OEBPS/chapter.xhtml": chapter,
            "OEBPS/nav.xhtml": NAV,
            **(extra or {}),
        }
        for name, data in files.items():
            archive.writestr(name, data)


def check(path: Path) -> dict:
    result = subprocess.run([str(CHECKER), str(path)], capture_output=True, text=True, check=False)
    return json.loads(result.stdout)


def test_unicode_structure_metadata_and_real_loaders(tmp_path: Path) -> None:
    source = tmp_path / "not-the-id.epub"
    fixture(source)
    output = tmp_path / "out"
    manifest = convert(source, output, CHECKER)
    assert manifest["identifier"] == "urn:isbn:9780000000001"
    assert manifest["metadata"]["title"] == ["Nav only title"]
    assert manifest["navigation"] == ["OEBPS/nav.xhtml"]
    assert manifest["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (output / "sources/original.epub").read_bytes() == source.read_bytes()
    assert (output / "documents/0001.txt").read_text() == "Áβcafé & 東京"
    doc = json.loads((output / "documents/0001.json").read_text())
    assert [
        (e["tag"], e["start"], e["end"]) for e in doc["elements"] if e["tag"] in {"h1", "em", "p"}
    ] == [("h1", 0, 2), ("em", 1, 2), ("p", 2, 11)]
    node = manifest["graph"]["node_ids"]["document:chapter"]
    assert {path.name for path in (output / "tf").iterdir() if path.is_dir()} == {"assets"}
    tf = Fabric(locations=str(output / "tf"), silent="deep").load(
        "text document xhtml_tag", silent="deep"
    )
    assert tf.T.text(node) == "Áβcafé & 東京"
    cf = ContextFabric(locations=str(output / "tf"))
    api = cf.loadAll()
    assert api.T.text(node) == "Áβcafé & 東京"
    second = tmp_path / "second"
    convert(source, second, CHECKER)
    first_tf = {p.name: p.read_bytes() for p in (output / "tf").glob("*.tf") if p.is_file()}
    assert first_tf == {p.name: p.read_bytes() for p in (second / "tf").glob("*.tf") if p.is_file()}


@pytest.mark.parametrize(
    ("opf", "chapter", "extra", "code"),
    [
        (OPF.replace(b'idref="chapter"', b'idref="missing"'), CHAPTER, None, "EPUB_SPINE"),
        (OPF.replace(b"urn:isbn:9780000000001", b" "), CHAPTER, None, "EPUB_IDENTIFIER"),
        (
            OPF.replace(b'<itemref idref="chapter"/>', b'<itemref idref="chapter" linear="no"/>'),
            CHAPTER,
            None,
            "EPUB_NONLINEAR",
        ),
        (OPF, CHAPTER.replace(b"<section>", b'<section><img src="a.png"/>'), None, "EPUB_ASSET"),
        (
            OPF,
            CHAPTER.replace(
                b"<section>",
                b'<section><aside xmlns:epub="http://www.idpf.org/2007/ops" epub:type="footnote">note</aside>',
            ),
            None,
            "EPUB_NOTE_ID",
        ),
        (
            OPF,
            CHAPTER.replace(b'xmlns="http://www.w3.org/1999/xhtml"', b'xmlns="urn:wrong"'),
            None,
            "EPUB_XHTML",
        ),
        (
            OPF.replace(b'href="chapter.xhtml"', b'href="missing.xhtml"'),
            CHAPTER,
            None,
            "EPUB_MANIFEST",
        ),
        (b'<!DOCTYPE package [<!ENTITY x "bad">]>' + OPF, CHAPTER, None, "EPUB_XML_DTD"),
        (OPF, CHAPTER, {"META-INF/encryption.xml": b"<encryption/>"}, "EPUB_ENCRYPTED"),
        (OPF, CHAPTER, {"huge.bin": b"x" * (16 * 1024 * 1024 + 1)}, "EPUB_LIMIT"),
        (OPF, CHAPTER, {"../escape": b"bad"}, "EPUB_PATH"),
    ],
)
def test_blocking_inputs(
    tmp_path: Path, opf: bytes, chapter: bytes, extra: dict[str, bytes] | None, code: str
) -> None:
    source = tmp_path / "bad.epub"
    fixture(source, opf=opf, chapter=chapter, extra=extra)
    report = check(source)
    assert code in [
        finding["code"] for item in report["findings"] for finding in item["report"]["diagnostics"]
    ]
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out", CHECKER)
    assert not (tmp_path / "out").exists()


def test_member_source_location_for_broken_spine(tmp_path: Path) -> None:
    source = tmp_path / "bad.epub"
    fixture(source, opf=OPF.replace(b'idref="chapter"', b'idref="missing"'))
    report = check(source)
    finding = next(
        item
        for item in report["findings"]
        if item["report"]["diagnostics"][0]["code"] == "EPUB_SPINE"
    )
    assert finding["member"] == "OEBPS/book.opf"
    position = finding["report"]["diagnostics"][0]["locations"][0]["start"]
    assert OPF.replace(b'idref="chapter"', b'idref="missing"')[position["byte"] :].startswith(
        b"<itemref"
    )


def test_archive_member_count_limit(tmp_path: Path) -> None:
    source = tmp_path / "too-many.epub"
    with ZipFile(source, "w", compression=ZIP_DEFLATED) as archive:
        for index in range(1025):
            archive.writestr(f"entry-{index}", b"")
    report = check(source)
    assert report["findings"][0]["report"]["diagnostics"][0]["code"] == "EPUB_LIMIT"


def test_member_location_distinguishes_bytes_and_scalars(tmp_path: Path) -> None:
    source = tmp_path / "bad.epub"
    modified = OPF.replace(b"Nav only title", "É title".encode()).replace(
        b'idref="chapter"', b'idref="missing"'
    )
    fixture(source, opf=modified)
    report = check(source)
    position = next(
        diagnostic["locations"][0]["start"]
        for item in report["findings"]
        for diagnostic in item["report"]["diagnostics"]
        if diagnostic["code"] == "EPUB_SPINE"
    )
    assert position["byte"] > position["scalar"]
    assert modified[position["byte"] :].startswith(b"<itemref")


def test_xml_error_location_after_unicode_uses_member_bytes(tmp_path: Path) -> None:
    source = tmp_path / "malformed.epub"
    chapter = (
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>'
        + "É 東京".encode()
        + b"<span>bad</em></p></body></html>"
    )
    fixture(source, chapter=chapter)
    report = check(source)
    diagnostic = next(
        diagnostic
        for finding in report["findings"]
        for diagnostic in finding["report"]["diagnostics"]
        if diagnostic["code"] == "EPUB_XML"
    )
    position = diagnostic["locations"][0]["start"]
    assert position["byte"] > position["scalar"]
    assert chapter[position["byte"] :].startswith(b"</em>")


def test_note_has_separate_slots_and_link_in_both_loaders(tmp_path: Path) -> None:
    source = tmp_path / "notes.epub"
    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>Alpha<a epub:type="noteref" href="#n1">1</a> omega<aside epub:type="footnote" id="n1"><p>Note beta</p></aside>!</p></body></html>"""
    fixture(source, chapter=chapter)
    output = tmp_path / "out"
    manifest = convert(source, output, CHECKER)
    assert (output / "documents/0001.txt").read_text() == "Alpha1 omega!"
    assert (output / "notes/0001.txt").read_text() == "Note beta"
    assert manifest["notes"] == ["OEBPS/chapter.xhtml#n1"]
    assert manifest["note_references"][0]["label"] == "1"
    doc_node = manifest["graph"]["node_ids"]["document:chapter"]
    note_node = manifest["graph"]["node_ids"]["note:OEBPS/chapter.xhtml#n1"]
    anchor_key = manifest["note_references"][0]["anchor_key"]
    anchor_node = manifest["graph"]["node_ids"]["document:chapter:" + anchor_key]
    assert {path.name for path in (output / "tf").iterdir() if path.is_dir()} == {"assets"}
    tf = Fabric(locations=str(output / "tf"), silent="deep").load(
        "text document noteref note_kind", silent="deep"
    )
    assert tf.T.text(doc_node) == "Alpha1 omega!"
    assert tf.T.text(note_node) == "Note beta"
    assert tf.E.noteref.f(anchor_node) == (note_node,)
    cf = ContextFabric(locations=str(output / "tf")).loadAll()
    assert cf.T.text(doc_node) == "Alpha1 omega!"
    assert cf.T.text(note_node) == "Note beta"
    assert cf.E.noteref.f(anchor_node) == (note_node,)
    other = tmp_path / "other"
    convert(source, other, CHECKER)
    assert {p.name: p.read_bytes() for p in (output / "tf").glob("*.tf") if p.is_file()} == {
        p.name: p.read_bytes() for p in (other / "tf").glob("*.tf") if p.is_file()
    }


def test_cross_member_note_reference_and_two_anchors(tmp_path: Path) -> None:
    source = tmp_path / "cross.epub"
    opf = OPF.replace(
        b'<item id="nav"',
        b'<item id="second" href="second.xhtml" media-type="application/xhtml+xml"/><item id="nav"',
    ).replace(b'<itemref idref="chapter"/>', b'<itemref idref="chapter"/><itemref idref="second"/>')
    first = b"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="second.xhtml#n">1</a>B<a epub:type="noteref" href="second.xhtml#n">*</a></p></body></html>"""
    second = b"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>CD</p><aside epub:type="endnote" id="n">End note</aside></body></html>"""
    fixture(source, opf=opf, chapter=first, extra={"OEBPS/second.xhtml": second})
    manifest = convert(source, tmp_path / "out", CHECKER)
    assert [r["target_key"] for r in manifest["note_references"]] == [
        "OEBPS/second.xhtml#n",
        "OEBPS/second.xhtml#n",
    ]
    assert (tmp_path / "out/documents/0001.txt").read_text() == "A1B*"
    assert (tmp_path / "out/documents/0002.txt").read_text() == "CD"
    assert (tmp_path / "out/notes/0001.txt").read_text() == "End note"


@pytest.mark.parametrize(
    ("chapter", "code"),
    [
        (
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#missing">1</a></p></body></html>',
            "EPUB_NOTE_REF",
        ),
        (
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A</p><aside epub:type="footnote" id="n">orphan</aside></body></html>',
            "EPUB_NOTE_ORPHAN",
        ),
        (
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#n"></a></p><aside epub:type="footnote" id="n">body</aside></body></html>',
            "EPUB_NOTE_REF",
        ),
        (
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#n">1</a></p><aside epub:type="footnote" id="n"></aside></body></html>',
            "EPUB_NOTE_ID",
        ),
        (
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#n">1</a></p><aside epub:type="footnote" id="n">one</aside><aside epub:type="footnote" id="n">two</aside></body></html>',
            "EPUB_NOTE_ID",
        ),
        (
            b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#n">1</a></p><aside epub:type="footnote" id="n">one<a epub:type="noteref" href="#n">nested</a></aside></body></html>',
            "EPUB_NOTE_NESTED",
        ),
    ],
)
def test_invalid_note_graph_blocks(tmp_path: Path, chapter: bytes, code: str) -> None:
    source = tmp_path / "bad-note.epub"
    fixture(source, chapter=chapter)
    report = check(source)
    assert code in [d["code"] for item in report["findings"] for d in item["report"]["diagnostics"]]
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out", CHECKER)


def test_broken_note_reference_has_member_byte_location(tmp_path: Path) -> None:
    source = tmp_path / "broken.epub"
    chapter = b'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#absent">1</a></p></body></html>'
    fixture(source, chapter=chapter)
    report = check(source)
    finding = next(
        (item, diagnostic)
        for item in report["findings"]
        for diagnostic in item["report"]["diagnostics"]
        if diagnostic["code"] == "EPUB_NOTE_REF"
    )
    assert finding[0]["member"] == "OEBPS/chapter.xhtml"
    position = finding[1]["locations"][0]["start"]
    assert chapter[position["byte"] :].startswith(b"<a epub:type")


def test_xhtml_dtd_and_images_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "illustrated.epub"
    dtd = b'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">\n'
    chapter = (
        dtd
        + b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Before<img src="art.png" alt="Illustration"/>After</p></body></html>'
    )
    opf = OPF.replace(
        b'<item id="nav"',
        b'<item id="art" href="art.png" media-type="image/png"/><item id="nav"',
    )
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000b49444154789c636000020000050001a5f645400000000049454e44ae426082"
    )
    fixture(source, opf=opf, chapter=chapter, extra={"OEBPS/art.png": png})
    output = tmp_path / "out"
    manifest = convert(source, output, CHECKER)
    assert (output / "documents/0001.txt").read_text() == "BeforeAfter"
    assert len(manifest["images"]) == 1
    image = manifest["images"][0]
    assert image["text_offset"] == 6
    assert image["source_byte"] == chapter.index(b"<img")
    assert image["alt"] == "Illustration"
    assert image["sha256"] == hashlib.sha256(png).hexdigest()
    assert (output / image["file"]).read_bytes() == png
    node = manifest["graph"]["node_ids"]["document:chapter"]
    tf = Fabric(locations=str(output / "tf"), silent="deep").load(
        "text image_assets", silent="deep"
    )
    cf = ContextFabric(locations=str(output / "tf")).loadAll()
    assert json.loads(tf.F.image_assets.v(node)) == [image]
    assert json.loads(cf.F.image_assets.v(node)) == [image]
    assert tf.T.text(node) == cf.T.text(node) == "BeforeAfter"
    second = tmp_path / "second"
    convert(source, second, CHECKER)
    assert {p.name: p.read_bytes() for p in (output / "tf").glob("*.tf") if p.is_file()} == {
        p.name: p.read_bytes() for p in (second / "tf").glob("*.tf") if p.is_file()
    }


def test_unsupported_dtd_blocks(tmp_path: Path) -> None:
    source = tmp_path / "unsafe.epub"
    chapter = b'<!DOCTYPE html [<!ENTITY a "secret">]><html xmlns="http://www.w3.org/1999/xhtml"><body><img src="art.svg"/></body></html>'
    opf = OPF.replace(
        b'<item id="nav"',
        b'<item id="art" href="art.svg" media-type="image/svg+xml"/><item id="nav"',
    )
    fixture(source, opf=opf, chapter=chapter, extra={"OEBPS/art.svg": b"<svg/>"})
    assert "EPUB_XML_DTD" in [
        d["code"] for f in check(source)["findings"] for d in f["report"]["diagnostics"]
    ]
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out", CHECKER)


def test_responsive_image_variant_blocks(tmp_path: Path) -> None:
    source = tmp_path / "responsive.epub"
    chapter = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>Text<img src="art.png" srcset="art.png 2x"/></p></body></html>'
    opf = OPF.replace(
        b'<item id="nav"',
        b'<item id="art" href="art.png" media-type="image/png"/><item id="nav"',
    )
    fixture(source, opf=opf, chapter=chapter, extra={"OEBPS/art.png": b"opaque-png"})
    assert "EPUB_ASSET" in [
        d["code"] for f in check(source)["findings"] for d in f["report"]["diagnostics"]
    ]
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out", CHECKER)


def test_svg_media_and_document_assets_have_tf_locations(tmp_path: Path) -> None:
    source = tmp_path / "assets.epub"
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="1" height="1"/></svg>'
    chapter = (
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>A'
        b'<img src="art.svg" alt="art"/>B' + svg + b'C<audio src="sound.mp3">fallback</audio>D'
        b'<video poster="poster.png"><source src="clip.mp4"/><track src="captions.vtt"/></video>E'
        b'<object data="paper.pdf">download</object>F</p></body></html>'
    )
    assets = {
        "art.svg": ("image/svg+xml", svg),
        "sound.mp3": ("audio/mpeg", b"opaque-audio"),
        "poster.png": ("image/png", b"opaque-png"),
        "clip.mp4": ("video/mp4", b"opaque-video"),
        "captions.vtt": ("text/vtt", b"WEBVTT\n\n"),
        "paper.pdf": ("application/pdf", b"%PDF-opaque"),
    }
    declarations = b"".join(
        f'<item id="asset-{index}" href="{name}" media-type="{media}"/>'.encode()
        for index, (name, (media, _)) in enumerate(assets.items())
    )
    opf = OPF.replace(b'<item id="nav"', declarations + b'<item id="nav"')
    fixture(
        source,
        opf=opf,
        chapter=chapter,
        extra={"OEBPS/" + name: data for name, (_, data) in assets.items()},
    )
    output = tmp_path / "out"
    manifest = convert(source, output, CHECKER)
    assert (output / "documents/0001.txt").read_text() == "ABCfallbackDEdownloadF"
    assert len(manifest["assets"]) == 7
    assert len(manifest["images"]) == 3
    assert [asset["kind"] for asset in manifest["assets"]] == [
        "image",
        "image",
        "audio",
        "image",
        "video",
        "track",
        "object",
    ]
    assert [asset["text_offset"] for asset in manifest["assets"]] == [1, 2, 3, 12, 12, 12, 13]
    for asset in manifest["assets"]:
        assert asset["file"].startswith("tf/assets/")
        assert asset["tf_path"].startswith("assets/")
        data = (output / asset["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == asset["sha256"]
        assert chapter[asset["source_byte"] :].startswith(b"<")
    inline = manifest["assets"][1]
    assert inline["source_end"] is not None
    assert (output / inline["file"]).read_bytes() == svg
    node = manifest["graph"]["node_ids"]["document:chapter"]
    tf = Fabric(locations=str(output / "tf"), silent="deep").load(
        "text asset_refs image_assets", silent="deep"
    )
    cf = ContextFabric(locations=str(output / "tf")).loadAll()
    for api in (tf, cf):
        assert api.T.text(node) == "ABCfallbackDEdownloadF"
        assert json.loads(api.F.asset_refs.v(node)) == manifest["assets"]
        assert json.loads(api.F.image_assets.v(node)) == manifest["images"]


def test_active_external_svg_blocks(tmp_path: Path) -> None:
    source = tmp_path / "active-svg.epub"
    chapter = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p>A<img src="art.svg"/>B</p></body></html>'
    opf = OPF.replace(
        b'<item id="nav"',
        b'<item id="art" href="art.svg" media-type="image/svg+xml"/><item id="nav"',
    )
    active = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
    fixture(source, opf=opf, chapter=chapter, extra={"OEBPS/art.svg": active})
    assert "EPUB_ASSET" in [
        d["code"] for f in check(source)["findings"] for d in f["report"]["diagnostics"]
    ]
    with pytest.raises(ConversionError):
        convert(source, tmp_path / "out", CHECKER)


def test_dark_qa_browser_compares_original_and_bundle(tmp_path: Path) -> None:
    source = tmp_path / "qa.epub"
    fixture(source)
    bundle = tmp_path / "bundle"
    convert(source, bundle, CHECKER)
    site = tmp_path / "site"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "packages/epub-to-tf/tools/qa_browser.py"),
            str(bundle),
            str(site),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    page = (site / "index.html").read_text()
    assert ":root{color-scheme:dark}" in page
    assert 'iframe id="source" class="source-view" sandbox=""' in page
    assert '"source": "Áβcafé & 東京"' in page
    assert '"tf": "Áβcafé & 東京"' in page


def test_note_image_and_inline_math_keep_scope_and_offsets(tmp_path: Path) -> None:
    source = tmp_path / "note-assets.epub"
    chapter = b"""<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><body><p>A<a epub:type="noteref" href="#n">1</a><math xmlns="http://www.w3.org/1998/Math/MathML"><mi>x</mi></math>B</p><aside epub:type="footnote" id="n">Note<img src="art.png"/> body</aside></body></html>"""
    opf = OPF.replace(
        b'<item id="nav"', b'<item id="art" href="art.png" media-type="image/png"/><item id="nav"'
    )
    fixture(source, opf=opf, chapter=chapter, extra={"OEBPS/art.png": b"opaque-image"})
    output = tmp_path / "out"
    manifest = convert(source, output, CHECKER)
    assert (output / "documents/0001.txt").read_text() == "A1B"
    assert (output / "notes/0001.txt").read_text() == "Note body"
    math, image = manifest["assets"]
    assert (math["scope"], math["kind"], math["media_type"], math["text_offset"]) == (
        "document",
        "math",
        "application/mathml+xml",
        2,
    )
    assert (image["scope"], image["scope_id"], image["kind"], image["text_offset"]) == (
        "note",
        "OEBPS/chapter.xhtml#n",
        "image",
        4,
    )
    assert (output / math["file"]).read_bytes() == chapter[math["source_byte"] : math["source_end"]]
    note_node = manifest["graph"]["node_ids"]["note:OEBPS/chapter.xhtml#n"]
    tf = Fabric(locations=str(output / "tf"), silent="deep").load("text asset_refs", silent="deep")
    cf = ContextFabric(locations=str(output / "tf")).loadAll()
    for api in (tf, cf):
        assert api.T.text(note_node) == "Note body"
        assert json.loads(api.F.asset_refs.v(note_node)) == [image]


def test_guarded_xhtml_repair_and_final_loader(tmp_path: Path) -> None:
    source = tmp_path / "malformed.epub"
    chapter = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="v">caf\xc3\xa9 <em>\xce\xb2</p><p id="v">\xe6\x9d\xb1\xe4\xba\xac</p></body></html>'
    fixture(source, chapter=chapter)
    assert "EPUB_XML" in [
        d["code"] for f in check(source)["findings"] for d in f["report"]["diagnostics"]
    ]
    output = tmp_path / "out"
    manifest = convert(source, output, CHECKER, repair=True)
    assert (output / "sources/original.epub").read_bytes() == source.read_bytes()
    assert (output / "sources/repaired.epub").is_file()
    assert manifest["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert manifest["source"]["sha256"] != manifest["validated_source"]["sha256"]
    assert [row["action"] for row in manifest["repair_ledger"]] == [
        "recover_xhtml",
        "disambiguate_unreferenced_ids",
    ]
    assert (output / "documents/0001.txt").read_text() == "café β東京"
    node = manifest["graph"]["node_ids"]["document:chapter"]
    assert (
        Fabric(locations=str(output / "tf"), silent="deep").load("text", silent="deep").T.text(node)
        == "café β東京"
    )
    assert ContextFabric(locations=str(output / "tf")).loadAll().T.text(node) == "café β東京"
    with ZipFile(output / "sources/repaired.epub") as archive:
        repaired = archive.read("OEBPS/chapter.xhtml")
    assert b"--tf-recovered-2" in repaired
    final = json.loads((output / "sources/validation.json").read_text())
    assert final["final_findings"] == []
    second = tmp_path / "second"
    convert(source, second, CHECKER, repair=True)
    assert (output / "sources/repaired.epub").read_bytes() == (
        second / "sources/repaired.epub"
    ).read_bytes()
    assert {
        path.name: path.read_bytes() for path in (output / "tf").glob("*.tf") if path.is_file()
    } == {path.name: path.read_bytes() for path in (second / "tf").glob("*.tf") if path.is_file()}
    site = tmp_path / "site"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "packages/epub-to-tf/tools/qa_browser.py"),
            str(output),
            str(site),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (site / "source/OEBPS/chapter.xhtml").read_bytes() == chapter
    assert (site / "validated/OEBPS/chapter.xhtml").read_bytes() == repaired
    assert "Show original XHTML" in (site / "index.html").read_text()


def test_repair_rejects_ambiguous_duplicate_id_link(tmp_path: Path) -> None:
    source = tmp_path / "ambiguous.epub"
    chapter = b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="v">One</p><p id="v">Two</p><a href="#v">ref</a></body></html>'
    fixture(source, chapter=chapter)
    with pytest.raises(ConversionError, match="duplicate ID has an inbound reference"):
        convert(source, tmp_path / "out", CHECKER, repair=True)
    assert not (tmp_path / "out").exists()


def test_repair_rejects_lost_source_attribute(tmp_path: Path) -> None:
    source = tmp_path / "duplicate-attribute.epub"
    chapter = (
        b'<html xmlns="http://www.w3.org/1999/xhtml"><body><p id="a" id="b">Text</p></body></html>'
    )
    fixture(source, chapter=chapter)
    with pytest.raises(ConversionError, match="lost source attributes"):
        convert(source, tmp_path / "out", CHECKER, repair=True)
    assert not (tmp_path / "out").exists()


def test_checker_explicit_slot_bound(tmp_path: Path) -> None:
    source = tmp_path / "limit.epub"
    fixture(source)
    limited = subprocess.run(
        [str(CHECKER), str(source), "--max-slots", "3"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert limited.returncode == 1
    assert any(
        d["code"] == "EPUB_LIMIT"
        for item in json.loads(limited.stdout)["findings"]
        for d in item["report"]["diagnostics"]
    )
    assert convert(source, tmp_path / "out", CHECKER, max_slots=100)["max_slots"] == 100
