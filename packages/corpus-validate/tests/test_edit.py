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
