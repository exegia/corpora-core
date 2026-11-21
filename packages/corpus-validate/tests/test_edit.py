"""Real Text-Fabric and Context-Fabric archive editing."""

import io
import zipfile

import pytest
from cfabric import Fabric as ContextFabric
from test_validator import archive_bytes

from corpus_validate import read_archive, validate_archive
from corpus_validate.edit import edit_archive

pytest_plugins = ("test_validator",)


@pytest.fixture
def corpus(tf_root):
    fabric = ContextFabric(locations=str(tf_root), silent="deep")
    assert fabric.loadAll(silent="deep")
    for existing in (tf_root / ".cfr").rglob("*.cfr"):
        existing.unlink()
    cache = tf_root / ".cfr" / "fixture.cfr"
    cache.parent.mkdir(exist_ok=True)
    fabric.compile(str(cache), silent="deep")
    data = archive_bytes(tf_root, ".corpus")
    report = validate_archive(data, "input.corpus")
    assert report["valid"], report["reasons"]
    return data


def test_node_edit_rebuilds_cache_and_preserves_other_nodes(corpus):
    changed = edit_archive(corpus, node=1, features={"word": "Changed Ω"})
    assert validate_archive(changed, "changed.corpus")["valid"]
    assert read_archive(changed, "node", node=1)["text"] == "Changed Ω"
    assert read_archive(changed, "node", node=2)["text"] == "βήτα"
    with zipfile.ZipFile(io.BytesIO(corpus)) as old, zipfile.ZipFile(io.BytesIO(changed)) as new:
        assert set(old.namelist()) - set(new.namelist()) == {
            path for path in old.namelist() if path.startswith("corpora/.tf/")
        }
        assert old.read("corpora/otype.tf") == new.read("corpora/otype.tf")
        assert old.read("corpora/.cfr/fixture.cfr") != new.read("corpora/.cfr/fixture.cfr")


def test_new_attribute_is_stored_and_visible(corpus):
    changed = edit_archive(corpus, node=1, features={"lemma": "λόγος"})
    assert read_archive(changed, "node", node=1)["features"]["lemma"] == "λόγος"
    assert "lemma" not in read_archive(changed, "node", node=2)["features"]


def test_manifest_edit_preserves_corpus_content(corpus):
    changed = edit_archive(corpus, manifest={"description": "Example"})
    assert read_archive(changed, "manifest")["description"] == "Example"
    assert read_archive(changed, "node", node=1)["text"] == "Alpha "


@pytest.mark.parametrize(
    "node,features",
    [
        (99, {"word": "x"}),
        (1, {"otype": "x"}),
        (1, {"word": 12}),
        (1, {"../bad": "x"}),
        (1, {"Word": "x"}),
    ],
)
def test_invalid_node_edits_fail(corpus, node, features):
    with pytest.raises(ValueError):
        edit_archive(corpus, node=node, features=features)


def test_numeric_attribute_can_be_changed_and_deleted(corpus):
    changed = edit_archive(corpus, node=4, features={"chapter": 4})
    assert read_archive(changed, "node", node=4)["features"]["chapter"] == 4
    removed = edit_archive(changed, node=4, features={"chapter": None})
    assert "chapter" not in read_archive(removed, "node", node=4)["features"]


def test_unsampled_stale_cache_is_rejected_before_edit(tmp_path):
    from tf.fabric import Fabric

    root = tmp_path / "tf"
    root.mkdir()
    words = {i: f"word{i} " for i in range(1, 31)}
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={"otype": {**{i: "word" for i in words}, 31: "book"}, "word": words},
        edgeFeatures={"oslots": {31: set(words)}},
        metaData={
            "otype": {"valueType": "str"},
            "word": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "otext": {"fmt:text-orig-full": "{word}"},
        },
        silent="deep",
    )
    fabric = ContextFabric(locations=str(root), silent="deep")
    assert fabric.loadAll(silent="deep")
    for existing in (root / ".cfr").rglob("*.cfr"):
        existing.unlink()
    cache = root / ".cfr" / "fixture.cfr"
    cache.parent.mkdir(exist_ok=True)
    fabric.compile(str(cache), silent="deep")
    words[2] = "changed-but-unsampled "
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={"word": words}, metaData={"word": {"valueType": "str"}}, silent="deep"
    )
    archive = archive_bytes(root, ".corpus")
    assert validate_archive(archive, "input.corpus")["valid"]
    with pytest.raises(ValueError, match="Source and Context-Fabric cache do not match"):
        edit_archive(archive, node=1, features={"word": "new"})


@pytest.mark.parametrize(
    ("text", "new_node", "words"),
    [
        ("One two three ", 6, ["One ", "two ", "three "]),
        ("Only", 4, ["Only"]),
        ("", 4, [""]),
        ("  One\nTwo  ", 5, ["  One\n", "Two  "]),
    ],
)
def test_structural_text_replacement_renumbers_and_rebuilds(corpus, text, new_node, words):
    changed = edit_archive(corpus, node=5, text_feature="word", text=text)
    verdict = validate_archive(changed, "changed.corpus")
    assert verdict["valid"], verdict["reasons"]
    assert read_archive(changed, "node", node=new_node)["text"] == text
    for index, expected in enumerate(words, start=1):
        assert read_archive(changed, "node", node=index)["text"] == expected
    assert read_archive(changed, "node", node=len(words) + 1)["features"]["book"] == "Mini"


def test_text_replacement_rejects_ambiguous_or_unknown_feature(corpus):
    with pytest.raises(ValueError, match="Text feature is unavailable"):
        edit_archive(corpus, node=5, text_feature="missing", text="new words")


@pytest.fixture
def linked_corpus(tmp_path):
    from tf.fabric import Fabric

    root = tmp_path / "linked"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {**{i: "word" for i in range(1, 6)}, 6: "book", 7: "passage", 8: "passage"},
            "word": {1: "A ", 2: "B ", 3: "C ", 4: "D ", 5: "E"},
            "label": {6: "Book", 7: "First", 8: "Second"},
        },
        edgeFeatures={"oslots": {6: {1, 2, 3, 4, 5}, 7: {2, 3}, 8: {4, 5}}, "xref": {8: {5}}},
        metaData={
            "otype": {"valueType": "str"},
            "word": {"valueType": "str"},
            "label": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "xref": {"valueType": "str"},
            "otext": {"fmt:text-orig-full": "{word}"},
        },
        silent="deep",
    )
    fabric = ContextFabric(locations=str(root), silent="deep")
    assert fabric.loadAll(silent="deep")
    for cache in (root / ".cfr").rglob("*.cfr"):
        cache.unlink()
    cache = root / ".cfr" / "fixture.cfr"
    cache.parent.mkdir(exist_ok=True)
    fabric.compile(str(cache), silent="deep")
    return archive_bytes(root, ".corpus")


def test_text_expansion_remaps_later_nodes_and_edges(linked_corpus, tmp_path):
    from tf.fabric import Fabric

    changed = edit_archive(linked_corpus, node=7, text_feature="word", text="New longer text ")
    assert read_archive(changed, "node", node=8)["text"] == "New longer text "
    assert read_archive(changed, "node", node=9)["text"] == "D E"
    assert read_archive(changed, "node", node=7)["text"] == "A New longer text D E"
    with zipfile.ZipFile(io.BytesIO(changed)) as archive:
        archive.extractall(tmp_path)
    api = Fabric(locations=str(tmp_path / "corpora"), silent="deep").loadAll(silent="deep")
    assert list(api.Es("xref").f(9)) == [6]


def test_text_contraction_rejects_a_removed_word_with_links(linked_corpus):
    with pytest.raises(ValueError, match="word links ambiguous"):
        edit_archive(linked_corpus, node=8, text_feature="word", text="Short")


def test_text_retokenization_refuses_unmapped_annotations(linked_corpus):
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(linked_corpus)) as source, zipfile.ZipFile(stream, "w") as out:
        for info in source.infolist():
            out.writestr(info, source.read(info))
        out.writestr("annotations.json", '{"nodes":{"2":{"note":"important"}}}')
    with pytest.raises(ValueError, match="annotations"):
        edit_archive(stream.getvalue(), node=7, text_feature="word", text="New longer text ")


def test_text_retokenization_rejects_partial_nested_node(linked_corpus, tmp_path):
    from tf.fabric import Fabric

    with zipfile.ZipFile(io.BytesIO(linked_corpus)) as archive:
        archive.extractall(tmp_path)
    root = tmp_path / "corpora"
    api = Fabric(locations=str(root), silent="deep").loadAll(silent="deep")
    types = dict(api.F.otype.items())
    slots = {int(n): set(values) for n, values in api.E.oslots.items()}
    types[9], slots[9] = "inline", {2}
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={"otype": types},
        edgeFeatures={"oslots": slots},
        metaData={"otype": dict(api.F.otype.meta), "oslots": dict(api.E.oslots.meta)},
        silent="deep",
    )
    for cache in (root / ".cfr").rglob("*.cfr"):
        cache.unlink()
    fabric = ContextFabric(locations=str(root), silent="deep")
    assert fabric.loadAll(silent="deep")
    for cache in (root / ".cfr").rglob("*.cfr"):
        cache.unlink()
    cache = root / ".cfr" / "fixture.cfr"
    fabric.compile(str(cache), silent="deep")
    with pytest.raises(ValueError, match="partially overlaps"):
        edit_archive(
            archive_bytes(root, ".corpus"), node=7, text_feature="word", text="New longer text "
        )


def test_text_feature_name_can_differ_from_slot_type(tmp_path):
    from tf.fabric import Fabric

    root = tmp_path / "tf"
    root.mkdir()
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {1: "word", 2: "word", 3: "passage"},
            "text": {1: "Old ", 2: "text"},
        },
        edgeFeatures={"oslots": {3: {1, 2}}},
        metaData={
            "otype": {"valueType": "str"},
            "text": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "otext": {"fmt:text-orig-full": "{text}"},
        },
        silent="deep",
    )
    fabric = ContextFabric(locations=str(root), silent="deep")
    assert fabric.loadAll(silent="deep")
    for cache in (root / ".cfr").rglob("*.cfr"):
        cache.unlink()
    cache = root / ".cfr" / "fixture.cfr"
    cache.parent.mkdir(exist_ok=True)
    fabric.compile(str(cache), silent="deep")
    changed = edit_archive(
        archive_bytes(root, ".corpus"), node=3, text_feature="text", text="New content here"
    )
    assert read_archive(changed, "node", node=4)["text"] == "New content here"


@pytest.mark.parametrize("single_level_epub_root", ["char", "character"], indirect=True)
def test_character_slots_stay_character_sized(single_level_epub_root):
    root = single_level_epub_root
    fabric = ContextFabric(locations=str(root), silent="deep")
    assert fabric.loadAll(silent="deep")
    for cache in (root / ".cfr").rglob("*.cfr"):
        cache.unlink()
    cache = root / ".cfr" / "fixture.cfr"
    cache.parent.mkdir(exist_ok=True)
    fabric.compile(str(cache), silent="deep")
    changed = edit_archive(
        archive_bytes(root, ".corpus"), node=4, text_feature="reading", text="XYZ"
    )
    assert read_archive(changed, "node", node=4)["text"] == "XYZ"
    assert [read_archive(changed, "node", node=i)["text"] for i in range(1, 4)] == ["X", "Y", "Z"]


def test_edit_rejects_cache_with_stale_text_format(linked_corpus):
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(linked_corpus)) as source, zipfile.ZipFile(stream, "w") as out:
        for info in source.infolist():
            content = source.read(info)
            if info.filename == "corpora/otext.tf":
                assert b"{word}" in content
                content = content.replace(b"{word}", b"{word}!")
            out.writestr(info, content)
    archive = stream.getvalue()
    assert validate_archive(archive, "input.corpus")["valid"]
    with pytest.raises(ValueError, match="Source and Context-Fabric cache do not match"):
        edit_archive(archive, node=7, features={"label": "changed"})


def test_replacing_one_word_with_multiple_words(linked_corpus):
    changed = edit_archive(linked_corpus, node=1, text_feature="word", text="New text ")
    assert read_archive(changed, "node", node=1)["text"] == "New "
    assert read_archive(changed, "node", node=2)["text"] == "text "
    assert read_archive(changed, "node", node=7)["text"] == "New text B C D E"


def test_text_edit_updates_converter_node_map_and_checksums(linked_corpus):
    import hashlib
    import json

    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(linked_corpus)) as source, zipfile.ZipFile(stream, "w") as out:
        hashes = {}
        for info in source.infolist():
            content = source.read(info)
            out.writestr(info, content)
            if not info.is_dir():
                hashes[info.filename] = hashlib.sha256(content).hexdigest()
        manifest = json.dumps(
            {
                "graph": {
                    "max_slot": 5,
                    "max_node": 8,
                    "node_ids": {"book": 6, "first": 7, "last": 8},
                }
            }
        ).encode()
        out.writestr("manifest.json", manifest)
        hashes["manifest.json"] = hashlib.sha256(manifest).hexdigest()
        out.writestr("checksums.json", json.dumps(hashes))
    changed = edit_archive(stream.getvalue(), node=7, text_feature="word", text="New longer text ")
    with zipfile.ZipFile(io.BytesIO(changed)) as result:
        graph = json.loads(result.read("manifest.json"))["graph"]
        assert graph == {
            "max_slot": 6,
            "max_node": 9,
            "node_ids": {"book": 7, "first": 8, "last": 9},
        }
        hashes = json.loads(result.read("checksums.json"))
        assert all(
            hashlib.sha256(result.read(name)).hexdigest() == digest
            for name, digest in hashes.items()
        )
        assert "corpora/word.tf" in hashes and "manifest.json" in hashes


def test_edit_rejects_tampered_converter_checksums(linked_corpus):
    stream = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(linked_corpus)) as source, zipfile.ZipFile(stream, "w") as out:
        for info in source.infolist():
            out.writestr(info, source.read(info))
        out.writestr("checksums.json", '{"corpora/word.tf":"' + "0" * 64 + '"}')
    with pytest.raises(ValueError, match="checksums do not match"):
        edit_archive(stream.getvalue(), node=1, features={"word": "changed"})
