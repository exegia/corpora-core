"""Real archive transformations prepare content without publishing it."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from uuid import uuid4

import pytest
import yaml
from cfabric import Fabric as ContextFabric
from test_validator import archive_bytes

from corpus_validate import read_archive, validate_archive
from corpus_validate.version_edit import prepare_edit, prepare_restore

pytest_plugins = ("test_validator",)


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


@pytest.fixture
def corpus(tf_root):
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    data = archive_bytes(tf_root, ".corpus")
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            if item.filename == "manifest.yml":
                target.writestr(item, "name: Mini\nversion: '1.0'\nextra: preserved\n")
            elif item.filename == "toc.yml":
                target.writestr(item, "version: 'v1.0'\ndocuments: []\n")
            else:
                target.writestr(item, source.read(item))
        target.writestr(
            "history.yml", "versions:\n  - id: v1.0\n    label: v1.0\n    current: true\n"
        )
        target.writestr("assets/empty/", b"")
        target.writestr("source.xml", b"<source>original</source>")
    return output.getvalue()


def options(data):
    return {
        "name": "mini.corpus",
        "expected_digest": digest(data),
        "expected_version": "1.0",
        "owner": str(uuid4()),
        "current_revision": str(uuid4()),
        "new_revision": str(uuid4()),
    }


def test_manifest_patch_preserves_other_members_and_appends_history(corpus):
    opts = options(corpus)
    result = prepare_edit(
        corpus,
        operation="manifest",
        updates={"name": "", "description": None, "version": "ignored", "unknown": "ignored"},
        **opts,
    )
    assert result.version == "v1.1" and result.digest == digest(result.archive)
    assert result.result["name"] == "" and result.result["description"] is None
    assert result.result["version"] == "1.1" and result.result["extra"] == "preserved"
    with (
        zipfile.ZipFile(io.BytesIO(corpus)) as before,
        zipfile.ZipFile(io.BytesIO(result.archive)) as after,
    ):
        for info in before.infolist():
            if info.filename not in {"manifest.yml", "history.yml", "toc.yml"}:
                assert after.read(info.filename) == before.read(info.filename)
        assert after.getinfo("assets/empty/").is_dir()
        assert yaml.safe_load(after.read("toc.yml"))["version"] == "v1.1"
        history = yaml.safe_load(after.read("history.yml"))["versions"]
    assert history[0]["snapshot_revision"] == opts["current_revision"] and not history[0]["current"]
    assert history[1]["snapshot_revision"] == opts["new_revision"] and history[1]["current"]
    assert history[1]["author"]["sub"] == opts["owner"]
    assert history[1]["snapshot_key"] is None
    assert validate_archive(result.archive, "edited.corpus")["valid"]
    assert read_archive(result.archive, "node", node=1)["otype"] == "word"


def test_node_annotation_preserves_original_type_and_notes(corpus):
    opts = options(corpus)
    first = prepare_edit(
        corpus, operation="node", node=1, updates={"otype": "  corrected  ", "note": ""}, **opts
    )
    assert first.result["otype"] == "corrected" and first.result["note"] == ""
    assert first.result["converted_otype"] == "word"
    with zipfile.ZipFile(io.BytesIO(first.archive)) as result:
        annotations = json.loads(result.read("annotations.json"))
    assert annotations["nodes"]["1"]["converted_otype"] == "word"
    with zipfile.ZipFile(io.BytesIO(first.archive)) as out:
        row = yaml.safe_load(out.read("history.yml"))["versions"][-1]
    assert {"path": "annotations.json", "kind": "added"} in row["files"]
    assert read_archive(first.archive, "node", node=1)["otype"] == "word"
    second = prepare_edit(
        first.archive,
        operation="node",
        node=1,
        updates={"note": "reviewed"},
        name="mini.corpus",
        expected_digest=first.digest,
        expected_version="1.1",
        owner=opts["owner"],
        current_revision=opts["new_revision"],
        new_revision=str(uuid4()),
    )
    assert second.result["converted_otype"] == "word" and second.result["otype"] == "corrected"
    assert second.result["note"] == "reviewed" and second.version == "v1.2"


def test_rejects_stale_unknown_and_invalid_edits(corpus):
    opts = options(corpus)
    with pytest.raises(ValueError, match="digest is stale"):
        prepare_edit(
            corpus,
            operation="manifest",
            updates={"name": "x"},
            **{**opts, "expected_digest": "sha256:stale"},
        )
    with pytest.raises(ValueError, match="version is stale"):
        prepare_edit(
            corpus,
            operation="manifest",
            updates={"name": "x"},
            **{**opts, "expected_version": "1.9"},
        )
    with pytest.raises(ValueError, match="Manifest update"):
        prepare_edit(corpus, operation="manifest", updates={"unknown": "x"}, **opts)
    with pytest.raises(ValueError, match="not present"):
        prepare_edit(corpus, operation="node", node=999, updates={"note": "x"}, **opts)
    with pytest.raises(ValueError, match="requires an otype or note"):
        prepare_edit(
            corpus, operation="node", node=1, updates={"otype": None, "note": None}, **opts
        )


def test_restore_keeps_current_timeline_and_creates_new_revision(corpus):
    opts = options(corpus)
    updated = prepare_edit(corpus, operation="node", node=1, updates={"note": "temporary"}, **opts)
    final_revision = str(uuid4())
    restored = prepare_restore(
        updated.archive,
        corpus,
        name="mini.corpus",
        expected_digest=updated.digest,
        selected_digest=digest(corpus),
        expected_version="1.1",
        selected_version="1.0",
        owner=opts["owner"],
        current_revision=opts["new_revision"],
        selected_revision=opts["current_revision"],
        new_revision=final_revision,
    )
    assert restored.version == "v1.2" and restored.digest == digest(restored.archive)
    assert read_archive(restored.archive, "manifest")["version"] == "1.2"
    assert read_archive(restored.archive, "node", node=1)["otype"] == "word"
    with zipfile.ZipFile(io.BytesIO(restored.archive)) as out:
        assert "annotations.json" not in out.namelist()
        assert out.getinfo("assets/empty/").is_dir()
        assert out.read("source.xml") == b"<source>original</source>"
        assert yaml.safe_load(out.read("toc.yml"))["version"] == "v1.2"
        history = yaml.safe_load(out.read("history.yml"))["versions"]
    assert [row["id"] for row in history] == ["v1.0", "v1.1", "v1.2"]
    assert [row["current"] for row in history] == [False, False, True]
    assert history[-1]["restored_from"] == {
        "version": "1.0",
        "snapshot_revision": opts["current_revision"],
    }
    assert history[-1]["snapshot_revision"] == final_revision
    assert {"path": "annotations.json", "kind": "removed"} in history[-1]["files"]
    assert validate_archive(restored.archive, "restored.corpus")["valid"]


def test_restore_rejects_wrong_snapshot_or_stale_digest(corpus):
    opts = options(corpus)
    updated = prepare_edit(corpus, operation="manifest", updates={"name": "new"}, **opts)
    restore = {
        "current_data": updated.archive,
        "selected_data": corpus,
        "name": "mini.corpus",
        "expected_digest": updated.digest,
        "selected_digest": digest(corpus),
        "expected_version": "1.1",
        "selected_version": "1.0",
        "owner": opts["owner"],
        "current_revision": opts["new_revision"],
        "selected_revision": opts["current_revision"],
        "new_revision": str(uuid4()),
    }
    with pytest.raises(ValueError, match="digest is stale"):
        prepare_restore(**{**restore, "selected_digest": "sha256:wrong"})
    with pytest.raises(ValueError, match="absent or ambiguous"):
        prepare_restore(**{**restore, "selected_revision": str(uuid4())})
    with pytest.raises(ValueError, match="version does not match"):
        prepare_restore(**{**restore, "selected_version": "1.9"})


def replace_member(data, name, replacement):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(data)) as source, zipfile.ZipFile(output, "w") as target:
        for item in source.infolist():
            if item.filename != name:
                target.writestr(item, source.read(item))
            elif replacement is not None:
                target.writestr(item, replacement)
        if name not in source.namelist() and replacement is not None:
            target.writestr(name, replacement)
    return output.getvalue()


def test_missing_history_gets_an_honest_packaged_baseline(corpus):
    data = replace_member(corpus, "history.yml", None)
    opts = options(data)
    edited = prepare_edit(data, operation="manifest", updates={"name": "new"}, **opts)
    with zipfile.ZipFile(io.BytesIO(edited.archive)) as output:
        history = yaml.safe_load(output.read("history.yml"))["versions"]
    assert len(history) == 2
    assert history[0]["title"] == "Packaged snapshot"
    assert history[0]["author"] is None and history[0]["at"] == ""
    assert all(isinstance(history[0][field], str) for field in ("id", "label", "title", "at"))
    assert history[0]["snapshot_revision"] == opts["current_revision"]
    assert history[1]["author"]["sub"] == opts["owner"]


def test_invalid_sidecars_toc_and_unsafe_names_fail_closed(corpus):
    bad_history = replace_member(corpus, "history.yml", b"versions: [invalid")
    with pytest.raises(ValueError, match="history"):
        prepare_edit(
            bad_history, operation="manifest", updates={"name": "new"}, **options(bad_history)
        )
    bad_toc = replace_member(corpus, "toc.yml", b"version: 'v9.9'\n")
    with pytest.raises(ValueError, match="contents version"):
        prepare_edit(bad_toc, operation="manifest", updates={"name": "new"}, **options(bad_toc))
    bad_annotations = replace_member(corpus, "annotations.json", b"{bad json")
    with pytest.raises(ValueError, match="annotations are invalid"):
        prepare_edit(
            bad_annotations,
            operation="node",
            node=1,
            updates={"note": "x"},
            **options(bad_annotations),
        )
    with pytest.raises(ValueError, match="plain .corpus"):
        prepare_edit(
            corpus,
            operation="manifest",
            updates={"name": "new"},
            **{**options(corpus), "name": "document.cusx"},
        )
    unsafe = replace_member(corpus, "../escape", b"bad")
    with pytest.raises(ValueError, match="archive is invalid"):
        prepare_edit(unsafe, operation="manifest", updates={"name": "new"}, **options(unsafe))


def test_restore_rejects_distinct_stable_corpus_id(corpus):
    original = replace_member(corpus, "manifest.yml", b"name: Mini\nuid: first\nversion: '1.0'\n")
    opts = options(original)
    current = prepare_edit(original, operation="manifest", updates={"name": "new"}, **opts)
    other = replace_member(original, "manifest.yml", b"name: Mini\nuid: second\nversion: '1.0'\n")
    with pytest.raises(ValueError, match="another corpus"):
        prepare_restore(
            current.archive,
            other,
            name="mini.corpus",
            expected_digest=current.digest,
            selected_digest=digest(other),
            expected_version="1.1",
            selected_version="1.0",
            owner=opts["owner"],
            current_revision=opts["new_revision"],
            selected_revision=opts["current_revision"],
            new_revision=str(uuid4()),
        )


def test_historical_revision_id_cannot_be_reused(corpus):
    opts = options(corpus)
    first = prepare_edit(corpus, operation="manifest", updates={"name": "first"}, **opts)
    second_revision = str(uuid4())
    second = prepare_edit(
        first.archive,
        operation="manifest",
        updates={"name": "second"},
        name="mini.corpus",
        expected_digest=first.digest,
        expected_version="1.1",
        owner=opts["owner"],
        current_revision=opts["new_revision"],
        new_revision=second_revision,
    )
    with pytest.raises(ValueError, match="reused snapshot revision"):
        prepare_edit(
            second.archive,
            operation="manifest",
            updates={"name": "third"},
            name="mini.corpus",
            expected_digest=second.digest,
            expected_version="1.2",
            owner=opts["owner"],
            current_revision=second_revision,
            new_revision=opts["current_revision"],
        )
    with pytest.raises(ValueError, match="reused snapshot revision"):
        prepare_restore(
            second.archive,
            first.archive,
            name="mini.corpus",
            expected_digest=second.digest,
            selected_digest=first.digest,
            expected_version="1.2",
            selected_version="1.1",
            owner=opts["owner"],
            current_revision=second_revision,
            selected_revision=opts["new_revision"],
            new_revision=opts["current_revision"],
        )


def test_restore_rejects_missing_selected_corpus_id(corpus):
    original = replace_member(corpus, "manifest.yml", b"name: Mini\nuid: first\nversion: '1.0'\n")
    opts = options(original)
    current = prepare_edit(original, operation="manifest", updates={"name": "new"}, **opts)
    with pytest.raises(ValueError, match="another corpus"):
        prepare_restore(
            current.archive,
            corpus,
            name="mini.corpus",
            expected_digest=current.digest,
            selected_digest=digest(corpus),
            expected_version="1.1",
            selected_version="1.0",
            owner=opts["owner"],
            current_revision=opts["new_revision"],
            selected_revision=opts["current_revision"],
            new_revision=str(uuid4()),
        )


def test_restore_rejects_stale_current_toc(corpus):
    opts = options(corpus)
    updated = prepare_edit(corpus, operation="manifest", updates={"name": "new"}, **opts)
    stale = replace_member(updated.archive, "toc.yml", b"version: 'v1.0'\ndocuments: []\n")
    with pytest.raises(ValueError, match="contents version"):
        prepare_restore(
            stale,
            corpus,
            name="mini.corpus",
            expected_digest=digest(stale),
            selected_digest=digest(corpus),
            expected_version="1.1",
            selected_version="1.0",
            owner=opts["owner"],
            current_revision=opts["new_revision"],
            selected_revision=opts["current_revision"],
            new_revision=str(uuid4()),
        )


def test_rejects_unsampled_stale_cache_on_edit_and_restore(tmp_path):
    from tf.fabric import Fabric

    tf_root = tmp_path / "many"
    tf_root.mkdir()
    assert Fabric(locations=str(tf_root), silent="deep").save(
        nodeFeatures={
            "otype": {**{node: "word" for node in range(1, 26)}, 26: "book"},
            "word": {node: f"w{node}" for node in range(1, 26)},
            "book": {26: "Mini"},
        },
        edgeFeatures={"oslots": {26: set(range(1, 26))}},
        metaData={
            "otype": {"valueType": "str"},
            "word": {"valueType": "str"},
            "book": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{word}",
                "sectionTypes": "book",
                "sectionFeatures": "book",
            },
        },
    )
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    clean = archive_bytes(tf_root, ".corpus")
    clean = replace_member(clean, "manifest.yml", b"name: Mini\nversion: '1.0'\n")
    clean = replace_member(
        clean, "history.yml", b"versions:\n  - id: v1.0\n    label: v1.0\n    current: true\n"
    )
    with zipfile.ZipFile(io.BytesIO(clean)) as source:
        words = source.read("corpora/word.tf")
    assert b"\nw2\n" in words
    stale = replace_member(clean, "corpora/word.tf", words.replace(b"\nw2\n", b"\nCHANGED\n", 1))
    # The general validator samples node 1, 3, ... and misses changed node 2.
    assert validate_archive(stale, "stale.corpus")["valid"]
    assert read_archive(stale, "node", node=2)["features"]["word"] == "w2"
    with pytest.raises(ValueError, match="cache does not match"):
        prepare_edit(stale, operation="node", node=2, updates={"note": "review"}, **options(stale))
    opts = options(clean)
    current = prepare_edit(clean, operation="manifest", updates={"name": "Current"}, **opts)
    with pytest.raises(ValueError, match="cache does not match"):
        prepare_restore(
            current.archive,
            stale,
            name="mini.corpus",
            expected_digest=current.digest,
            selected_digest=digest(stale),
            expected_version="1.1",
            selected_version="1.0",
            owner=opts["owner"],
            current_revision=opts["new_revision"],
            selected_revision=opts["current_revision"],
            new_revision=str(uuid4()),
        )


def test_rejects_stale_rendering_configuration_even_if_selected_text_matches(tf_root):
    from tf.fabric import Fabric

    assert Fabric(locations=str(tf_root), silent="deep").save(
        nodeFeatures={"alternate": {1: "Alpha ", 2: "different"}},
        metaData={"alternate": {"valueType": "str"}},
    )
    assert ContextFabric(locations=str(tf_root), silent="deep").loadAll(silent="deep")
    data = archive_bytes(tf_root, ".corpus")
    data = replace_member(data, "manifest.yml", b"name: Mini\nversion: '1.0'\n")
    data = replace_member(
        data, "history.yml", b"versions:\n  - id: v1.0\n    label: v1.0\n    current: true\n"
    )
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        otext = source.read("corpora/otext.tf")
    assert b"{word}" in otext
    stale = replace_member(data, "corpora/otext.tf", otext.replace(b"{word}", b"{alternate}"))
    assert validate_archive(stale, "stale.corpus")["valid"]
    with pytest.raises(ValueError, match="cache does not match"):
        prepare_edit(stale, operation="node", node=1, updates={"note": "review"}, **options(stale))


def test_render_comparison_has_a_work_bound():
    from types import SimpleNamespace

    from corpus_validate import ArchiveTooLarge
    from corpus_validate.version_edit import _full_render_hash

    api = SimpleNamespace(
        T=SimpleNamespace(formats={"one": None, "two": None}),
        F=SimpleNamespace(otype=SimpleNamespace(maxSlot=2_500_001)),
    )
    with pytest.raises(ArchiveTooLarge, match="workload limit"):
        _full_render_hash(api)
