"""Archive boundaries and real TF/CF loader acceptance."""

import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cfabric.core import Fabric as ContextFabric
from tf.fabric import Fabric

from corpus_validate import UnsupportedFormat, validate_archive
from corpus_validate.profiles import CUSX_PROFILE, CUSX_STREAM, _cusx_xml


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
    assert (tf_root / ".cfm").is_dir()

    result = validate_archive(archive_bytes(tf_root, ".corpus"), "mini.corpus")

    assert result["valid"], result["reasons"]
    assert result["checks"]["shipped_cfm_load"]
    assert result["checks"]["shipped_cfm_match"]


def test_corrupt_shipped_cache_is_not_silently_recompiled(tf_root: Path) -> None:
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    cache_files = [path for path in (tf_root / ".cfm").rglob("*") if path.is_file()]
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
