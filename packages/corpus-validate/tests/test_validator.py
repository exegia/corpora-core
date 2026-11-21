"""Archive boundaries and real TF/CF loader acceptance."""

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cfabric import Fabric as ContextFabric
from tf.fabric import Fabric

from corpus_validate import ArchiveReadNotFound, UnsupportedFormat, read_archive, validate_archive
from corpus_validate.ai_archive import StaleScope, validate_archive_scope
from corpus_validate.ai_types import NodeScope, ScopeLevel
from corpus_validate.profiles import CUSX_PROFILE, CUSX_STREAM, _cusx_xml, _resolved_target
from corpus_validate.reference import reference_archive
from corpus_validate.tfref import ParseError, SectionNotFound, VersionMismatch


def archive_bytes(root: Path, suffix: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, f"corpora/{path.relative_to(root).as_posix()}")
        if suffix == ".corpus":
            archive.writestr("manifest.yml", "name: mini\nformat: corpus\n")
            archive.writestr("toc.yml", "documents: []\n")
    return stream.getvalue()


@pytest.fixture
def tf_root(tmp_path: Path) -> Path:
    root = tmp_path / "tf"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {1: "word", 2: "word", 3: "book", 4: "chapter", 5: "verse"},
            "word": {1: "Alpha ", 2: "βήτα"},
            "book": {3: "Mini"},
            "chapter": {4: 1},
            "verse": {5: 1},
        },
        edgeFeatures={"oslots": {3: {1, 2}, 4: {1, 2}, 5: {1, 2}}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "word": {"valueType": "str"},
            "book": {"valueType": "str"},
            "chapter": {"valueType": "int"},
            "verse": {"valueType": "int"},
            "otext": {
                "fmt:text-orig-full": "{word}",
                "sectionTypes": "book,chapter,verse",
                "sectionFeatures": "book,chapter,verse",
            },
        },
    )
    return root


@pytest.fixture
def single_level_epub_root(tmp_path: Path, request: pytest.FixtureRequest) -> Path:
    slot = getattr(request, "param", "char")
    root = tmp_path / "epub-tf"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {1: slot, 2: slot, 3: slot, 4: "document", 5: "element", 6: "note"},
            "text": {1: "A", 2: "β", 3: "!"},
            "reading": {1: "A", 2: "β", 3: ""},
            "document": {4: "Doc"},
        },
        edgeFeatures={"oslots": {4: {1, 2, 3}, 5: {1, 2, 3}, 6: {3}}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "text": {"valueType": "str"},
            "reading": {"valueType": "str"},
            "document": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{reading}",
                "fmt:text-source-full": "{text}",
                "sectionTypes": "document",
                "sectionFeatures": "document",
            },
        },
    )
    return root


def test_real_text_fabric_and_context_fabric_round_trip(tf_root: Path) -> None:
    result = validate_archive(archive_bytes(tf_root, ".zip"), "mini.zip")

    assert result["valid"], result["reasons"]
    assert result["stats"]["max_slot"] == 2
    assert result["checks"]["text_fabric_load"]
    assert result["checks"]["context_fabric_load"]
    assert result["checks"]["cfm_mmap_reload"]
    assert result["checks"]["stats_match"]
    assert result["checks"]["samples_match"]
    assert result["checks"]["shipped_cfm_load"] is None
    assert result["checks"]["shipped_cfm_match"] is None


def test_shipped_cache_matches_fresh_compilation(tf_root: Path) -> None:
    api = ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    assert api
    assert (tf_root / ".cfr").is_dir()

    result = validate_archive(archive_bytes(tf_root, ".corpus"), "mini.corpus")

    assert result["valid"], result["reasons"]
    assert result["checks"]["shipped_cfm_load"]
    assert result["checks"]["shipped_cfm_match"]


def test_read_archive_views_open_the_shipped_cache(tf_root: Path) -> None:
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    archive = archive_bytes(tf_root, ".corpus")

    manifest = read_archive(archive, "manifest")
    index = read_archive(archive, "index")
    sections = read_archive(archive, "sections", limit=1)
    ref = index["sections"]["items"][0]["children"][0]["ref"]
    content = read_archive(archive, "content", ref=ref, limit=1)
    node = read_archive(archive, "node", node=1)

    assert manifest["name"] == "mini"
    assert index["sections"]["levels"] == ["book", "chapter", "verse"]
    assert sections["items"][0]["ref"] == "Mini"
    assert content["total"] == 1
    assert content["passages"][0]["node"] == 5
    assert [token["node"] for token in content["passages"][0]["tokens"]] == [1, 2]
    assert node["node"] == 1
    assert node["otype"] == "word"
    assert node["features"]["word"].strip() == "Alpha"
    assert node["annotation"] is None


def test_scope_validation_uses_real_archive_and_rejects_stale_version(tf_root: Path) -> None:
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    source = io.BytesIO(archive_bytes(tf_root, ".corpus"))
    output = io.BytesIO()
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(output, "w") as archive:
        for item in old.infolist():
            if item.filename != "manifest.yml":
                archive.writestr(item.filename, old.read(item))
        archive.writestr("manifest.yml", "name: mini\nversion: '1.0'\n")
    scope = NodeScope(corpus="mini", level=ScopeLevel.word, node_id=1, label="word", version="1.0")
    result = validate_archive_scope(output.getvalue(), scope)
    assert result.corpus == "mini" and result.version == "1.0" and result.checked_nodes == 1
    stale = NodeScope(corpus="mini", level=ScopeLevel.word, node_id=1, label="word", version="old")
    with pytest.raises(StaleScope):
        validate_archive_scope(output.getvalue(), stale)
    changed = NodeScope(
        corpus="mini",
        level=ScopeLevel.word,
        node_id=1,
        label="word",
        version="1.0",
        content_hash="sha256:" + "0" * 64,
    )
    with pytest.raises(StaleScope, match="Scoped text"):
        validate_archive_scope(output.getvalue(), changed)
    unknown = NodeScope(corpus="mini", level=ScopeLevel.word, node_id=999, label="x", version="1.0")
    with pytest.raises(ValueError, match="Unknown node"):
        validate_archive_scope(output.getvalue(), unknown)


def test_reference_roundtrip_against_real_context_fabric(tf_root: Path) -> None:
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    raw = io.BytesIO(archive_bytes(tf_root, ".corpus"))
    output = io.BytesIO()
    with zipfile.ZipFile(raw) as source, zipfile.ZipFile(output, "w") as archive:
        for item in source.infolist():
            if item.filename != "manifest.yml":
                archive.writestr(item.filename, source.read(item))
        archive.writestr("manifest.yml", "name: Mini\nversion: '2.3'\n")
    data = output.getvalue()
    created = reference_archive(data, "mini", node=1, end_node=2)
    assert created["ref"] == "mini@2.3/Mini:1:1!word1-2"
    assert created["nodes"] == [1, 2]
    assert reference_archive(data, "mini", ref=created["urn"])["nodes"] == [1, 2]
    assert reference_archive(data, "mini", ref=created["token"])["ref"] == created["ref"]
    revision = "a" * 40
    pinned = reference_archive(data, "mini", node=1, version=revision)
    assert f"@{revision}/" in pinned["ref"]
    assert reference_archive(data, "mini", ref=pinned["urn"], version=revision)["node"] == 1
    with pytest.raises(VersionMismatch):
        reference_archive(data, "mini", ref=pinned["ref"], version="b" * 40)
    assert (
        reference_archive(data, "mini", ref=created["ref"], shortcode=True)["ref"] == created["ref"]
    )
    with pytest.raises(VersionMismatch):
        reference_archive(data, "mini", ref="mini@old/Mini:1:1!word1")
    with pytest.raises(SectionNotFound):
        reference_archive(data, "mini", ref="mini@2.3/Missing:1:1")
    with pytest.raises(ParseError, match="does not match"):
        reference_archive(data, "mini", ref="other@2.3/Mini:1:1!word1")
    with pytest.raises(ParseError, match="does not match"):
        reference_archive(data, "mini", ref=created["token"].replace("comini_", "coother_"))


def test_shortcode_escapes_html_attributes() -> None:
    from corpus_validate import refdisplay, tfref

    payload = refdisplay.shortcode_payload(
        tfref.parse("mini/Book%22%3E:1"), 'mini/Book">:1', url_template='/r?ref={ref}&x="'
    )
    assert "&amp;x=&quot;" in payload["html"]
    assert "Book&quot;&gt;" in payload["html"]


def test_versions_preserve_history_and_fall_back_to_manifest() -> None:
    def bundle(history: str | bytes | None) -> bytes:
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr("manifest.yml", "name: Example\nversion: '1.2'\n")
            if history is not None:
                archive.writestr("history.yml", history)
        return stream.getvalue()

    history = "versions:\n  - id: v1.0\n    current: false\n    snapshot_key: original\n"
    assert read_archive(bundle(history), "versions") == {
        "versions": [{"id": "v1.0", "current": False, "snapshot_key": "original"}]
    }
    for absent in (None, "versions: []", "[invalid", b"\xff"):
        assert read_archive(bundle(absent), "versions") == {
            "versions": [
                {
                    "id": "packaged",
                    "sha": None,
                    "label": "1.2",
                    "title": "Converted",
                    "at": "",
                    "current": True,
                    "notes": ["Example"],
                }
            ]
        }


def test_single_level_sections_are_passages_and_tokens_use_requested_format(
    single_level_epub_root: Path,
) -> None:
    archive = archive_bytes(single_level_epub_root, ".zip")

    default = read_archive(archive, "content")
    source = read_archive(archive, "content", fmt="text-source-full", ref="Doc")

    assert [passage["node"] for passage in default["passages"]] == [4]
    assert [token["text"] for token in default["passages"][0]["tokens"]] == ["A", "β", ""]
    assert [passage["node"] for passage in source["passages"]] == [4]
    assert [token["text"] for token in source["passages"][0]["tokens"]] == ["A", "β", "!"]


def test_single_level_paginated_passages_cover_the_document(tmp_path: Path) -> None:
    root = tmp_path / "single-level"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {
                1: "word",
                2: "word",
                3: "word",
                4: "word",
                5: "document",
                6: "paragraph",
                7: "paragraph",
            },
            "word": {1: "one ", 2: "two ", 3: "three ", 4: "four"},
            "document": {5: "Doc"},
        },
        edgeFeatures={"oslots": {5: {1, 2, 3, 4}, 6: {1, 2}, 7: {3, 4}}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "word": {"valueType": "str"},
            "document": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{word}",
                "sectionTypes": "document",
                "sectionFeatures": "document",
            },
        },
    )
    archive = archive_bytes(root, ".zip")
    for ref in (None, "Doc"):
        first = read_archive(archive, "content", ref=ref, offset=0, limit=1)
        second = read_archive(archive, "content", ref=ref, offset=1, limit=1)
        assert first["total"] == second["total"] == 2
        assert first["next_offset"] == 1 and second["next_offset"] is None
        assert [first["passages"][0]["node"], second["passages"][0]["node"]] == [6, 7]
        assert [
            token["node"] for page in (first, second) for token in page["passages"][0]["tokens"]
        ] == [1, 2, 3, 4]


@pytest.mark.parametrize("element_slots", [({1, 2, 3}, {2}), ({1, 2}, {2, 3})])
def test_single_level_overlapping_elements_do_not_repeat_slots(
    tmp_path: Path, element_slots: tuple[set[int], set[int]]
) -> None:
    root = tmp_path / "overlapping-elements"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {1: "word", 2: "word", 3: "word", 4: "document", 5: "element", 6: "element"},
            "word": {1: "A", 2: "B", 3: "C"},
            "document": {4: "Doc"},
        },
        edgeFeatures={"oslots": {4: {1, 2, 3}, 5: element_slots[0], 6: element_slots[1]}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "word": {"valueType": "str"},
            "document": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{word}",
                "sectionTypes": "document",
                "sectionFeatures": "document",
            },
        },
    )
    archive = archive_bytes(root, ".zip")
    for ref in (None, "Doc"):
        result = read_archive(archive, "content", ref=ref, limit=1)
        assert result["total"] == 1
        assert result["next_offset"] is None
        assert result["passages"][0]["text"] == "ABC"
        assert [token["node"] for token in result["passages"][0]["tokens"]] == [1, 2, 3]


def test_default_tokens_keep_spacing_in_after_only(tmp_path: Path) -> None:
    root = tmp_path / "spaced-tf"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {1: "word", 2: "word", 3: "document"},
            "text": {1: "one", 2: "two"},
            "after": {1: " ", 2: "!"},
            "document": {3: "Doc"},
        },
        edgeFeatures={"oslots": {3: {1, 2}}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "text": {"valueType": "str"},
            "after": {"valueType": "str"},
            "document": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{text}{after}",
                "sectionTypes": "document",
                "sectionFeatures": "document",
            },
        },
    )
    archive = archive_bytes(root, ".zip")
    default = read_archive(archive, "content")["passages"][0]["tokens"]
    explicit = read_archive(archive, "content", fmt="text-orig-full")["passages"][0]["tokens"]
    assert [(token["text"], token["after"]) for token in default] == [("one", " "), ("two", "!")]
    assert [token["text"] for token in explicit] == ["one ", "two!"]


def test_lowest_section_content_covers_all_its_slots(spanning_fixture: Path) -> None:
    data = archive_bytes(spanning_fixture, ".corpus")
    all_passages = read_archive(data, "content")
    paragraph = next(p for p in all_passages["passages"] if p["node"] == 23)
    selected = read_archive(data, "content", ref=paragraph["ref"])
    assert [p["node"] for p in selected["passages"]] == [23]
    assert [t["node"] for t in selected["passages"][0]["tokens"]] == [1, 2, 3, 4]


def test_read_archive_rejects_missing_nodes_and_section_refs(tf_root: Path) -> None:
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    archive = archive_bytes(tf_root, ".corpus")

    with pytest.raises(ArchiveReadNotFound, match="Node 99"):
        read_archive(archive, "node", node=99)
    with pytest.raises(ArchiveReadNotFound, match="not found"):
        read_archive(archive, "content", ref="missing")


def test_corrupt_shipped_cache_is_not_silently_recompiled(tf_root: Path) -> None:
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    cache_files = [path for path in (tf_root / ".cfr").rglob("*") if path.is_file()]
    assert cache_files
    cache_files[0].write_bytes(b"corrupt cache")

    result = validate_archive(archive_bytes(tf_root, ".corpus"), "bad.corpus")

    assert result["valid"] is False
    assert result["checks"]["shipped_cfm_load"] is False


def test_unreadable_archive_is_a_failed_verdict() -> None:
    result = validate_archive(b"not a zip", "mini.corpus")
    assert result["valid"] is False
    assert result["checks"] == {"archive": False}


def test_unsupported_format_is_rejected() -> None:
    with pytest.raises(UnsupportedFormat):
        validate_archive(b"anything", "mini.pdf")


def test_archive_member_escape_is_rejected() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("../outside.tf", "data")
    result = validate_archive(stream.getvalue(), "mini.zip")
    assert not result["valid"]
    assert result["checks"] == {"archive": False}


def test_large_declared_node_range_is_rejected_before_loading() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("corpora/otype.tf", "@node\n\n1-1000001\tword\n")
    result = validate_archive(stream.getvalue(), "oversized.zip")
    assert result["valid"] is False
    assert "1000000 nodes" in result["reasons"][0]


def test_implicit_node_after_large_explicit_range_is_rejected() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("corpora/otype.tf", "@node\n\n1-1000000\tword\nbook\n")
    result = validate_archive(stream.getvalue(), "oversized.zip")
    assert result["valid"] is False
    assert "1000000 nodes" in result["reasons"][0]


def test_corrupt_compressed_member_is_a_failed_verdict() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", "A" * 500)
    raw = bytearray(stream.getvalue())
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        offset = archive.infolist()[0].header_offset + 30 + len("manifest.json")
    raw[offset] = 0x07
    result = validate_archive(bytes(raw), "broken.cusx")
    assert result["valid"] is False
    assert result["checks"]["cusx_package_integrity"] is False


def test_cusx_profile_accepts_matching_projection_and_hashes() -> None:
    document = {
        "metadata": {"source_format": "plain"},
        "units": [{"type": "paragraph", "tokens": [{"text": "Alpha", "after": ""}]}],
    }
    xml = _cusx_xml(document)
    identity = {"revision": "sha256:" + hashlib.sha256(xml).hexdigest()}
    members = {
        "document.usx": xml,
        "document.json": json.dumps(document).encode(),
        "snapshot.json": json.dumps(
            {"endpoint": identity, "stream_id": CUSX_STREAM, "text": "Alpha\n\n"}
        ).encode(),
        "references.json": b"[]",
        "mappings.json": b'{"mappings":[]}',
    }
    manifest = {
        "format": CUSX_PROFILE,
        "files": {
            name: "sha256:" + hashlib.sha256(data).hexdigest() for name, data in members.items()
        },
        "identity": identity,
        "stream": {"id": CUSX_STREAM, "offset_unit": "unicode-scalar", "normalization": "preserve"},
    }
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, data in members.items():
            archive.writestr(name, data)

    result = validate_archive(stream.getvalue(), "mini.cusx")

    assert result["valid"], result["reasons"]
    assert result["checks"]["cusx_package_integrity"]
    assert result["stats"] == {"documents": 1, "characters": 7, "units": 1}


def test_ctei_missing_required_members_is_invalid() -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("manifest.yml", "format: corpus")
    result = validate_archive(stream.getvalue(), "mini.ctei")
    assert result["valid"] is False
    assert result["checks"]["archive"] is False


@pytest.mark.parametrize("suffix", ["ctei", "cusx"])
def test_legacy_profile_fixtures_validate(suffix: str) -> None:
    fixture = Path(__file__).parent / "fixtures" / f"mini.{suffix}"
    result = validate_archive(fixture.read_bytes(), fixture.name)

    assert result["valid"], result["reasons"]
    assert result["stats"]["documents"] == 1


def test_ctei_tampered_reading_fails_hash_check() -> None:
    fixture = Path(__file__).parent / "fixtures" / "mini.ctei"
    output = io.BytesIO()
    with zipfile.ZipFile(fixture) as source, zipfile.ZipFile(output, "w") as archive:
        for member in source.namelist():
            data = source.read(member)
            if member.endswith("d001.xml"):
                data = data.replace(b"Exact", b"Wrong")
            archive.writestr(member, data)

    result = validate_archive(output.getvalue(), "tampered.ctei")

    assert result["valid"] is False
    assert "hashes" in result["reasons"][0]


def test_ctei_rejects_external_resolved_reference() -> None:
    document = "version_1.0.0/d001.xml"
    assert _resolved_target(document, "#n00001") == "version_1.0.0/d001.xml#n00001"
    with pytest.raises(ValueError, match="external target"):
        _resolved_target(document, "https://example.org#n00001")


def test_cli_emits_one_json_result_for_real_loader(tf_root: Path, tmp_path: Path) -> None:
    archive = tmp_path / "mini.zip"
    archive.write_bytes(archive_bytes(tf_root, ".zip"))

    result = subprocess.run(
        [sys.executable, "-m", "corpus_validate.cli", str(archive), "--name", "mini.zip"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["valid"] is True
    assert len(result.stdout.splitlines()) == 1
