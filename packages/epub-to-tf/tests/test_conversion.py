"""Independent reading expectations and loader acceptance for a tiny EPUB."""

import hashlib
import json
import subprocess
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
    assert not any(path.is_dir() for path in (output / "tf").iterdir())
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
        (OPF, CHAPTER.replace(b"<section>", b'<section><img src="a.png"/>'), None, "EPUB_CONTENT"),
        (
            OPF,
            CHAPTER.replace(
                b"<section>",
                b'<section><aside xmlns:epub="http://www.idpf.org/2007/ops" epub:type="footnote">note</aside>',
            ),
            None,
            "EPUB_NOTE",
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
