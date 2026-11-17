"""Real-loader content pagination preserves every selected source slot, in order."""

import io
import json
import zipfile
from pathlib import Path

import pytest
from cfabric import Fabric as ContextFabric
from tf.fabric import Fabric

from corpus_validate import read_archive


def corpus(
    tmp_path: Path,
    passages: tuple[set[int], set[int]],
    *,
    book_slots: set[int] | None = None,
    sections: bool = True,
    shipped_cache: bool = True,
    chapters: bool = False,
) -> bytes:
    root = tmp_path / "tf"
    root.mkdir()
    otext = {"fmt:text-orig-full": "{word}"}
    if sections:
        otext.update(sectionTypes="book,passage", sectionFeatures="book,passage")
    if chapters:
        otext.update(sectionTypes="book,chapter,passage", sectionFeatures="book,chapter,passage")
    assert Fabric(locations=str(root), silent="deep").save(
        nodeFeatures={
            "otype": {
                **dict.fromkeys(range(1, 6), "word"),
                6: "book",
                7: "passage",
                8: "passage",
                **({9: "chapter", 10: "chapter"} if chapters else {}),
            },
            "word": dict(enumerate(("In ", "the ", "gap ", "and ", "out."), 1)),
            "book": {6: "Mini"},
            "passage": {7: "A", 8: "B"},
            "annotation": {3: "uncovered"},
            **({"chapter": {9: 1, 10: 2}} if chapters else {}),
        },
        edgeFeatures={
            "oslots": {
                6: set(range(1, 6)) if book_slots is None else book_slots,
                7: passages[0],
                8: passages[1],
                **({9: {1, 2, 3}, 10: {4, 5}} if chapters else {}),
            }
        },
        metaData={
            **{
                name: {"valueType": "str"}
                for name in ("otype", "oslots", "word", "book", "passage", "annotation")
            },
            "otext": otext,
            **({"chapter": {"valueType": "int"}} if chapters else {}),
        },
    )
    if shipped_cache:
        assert ContextFabric(locations=str(root), silent="deep").loadAll(silent="deep")
        assert any((root / ".cfr").rglob("*.cfr"))
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in root.rglob("*"):
            if path.is_file():
                archive.write(path, f"corpora/{path.relative_to(root).as_posix()}")
        archive.writestr("manifest.yml", "name: Mini\nversion: '1.0'\nformat: corpus\n")
        archive.writestr("annotations.json", json.dumps({"nodes": {"3": {"note": "keep me"}}}))
    return result.getvalue()


@pytest.mark.parametrize("shipped_cache", [False, True], ids=["cold", "shipped"])
@pytest.mark.parametrize(
    "passages",
    [({1, 2}, {4, 5}), ({1, 2, 3}, {3, 4, 5}), ({1, 3, 5}, {2, 4})],
    ids=["gap", "overlap", "interleaved"],
)
def test_multilevel_fallback_preserves_complete_text_and_identity(
    tmp_path: Path, passages: tuple[set[int], set[int]], shipped_cache: bool
) -> None:
    archive = corpus(tmp_path, passages, shipped_cache=shipped_cache)
    for ref in (None, "Mini"):
        page = read_archive(archive, "content", ref=ref, limit=1)
        assert page["total"] == 1 and page["next_offset"] is None
        assert [p["node"] for p in page["passages"]] == [6]
        assert page["passages"][0]["text"] == "In the gap and out."
        assert [t["node"] for t in page["passages"][0]["tokens"]] == [1, 2, 3, 4, 5]
        assert read_archive(archive, "content", ref=ref, offset=1)["passages"] == []
    node = read_archive(archive, "node", node=3)
    assert node["text"] == "gap "
    assert node["features"]["annotation"] == "uncovered"
    assert node["annotation"] == {"note": "keep me"}


def test_complete_multilevel_passages_keep_fine_pagination(tmp_path: Path) -> None:
    archive = corpus(tmp_path, ({1, 2, 3}, {4, 5}))
    for ref in (None, "Mini"):
        first = read_archive(archive, "content", ref=ref, limit=1)
        second = read_archive(archive, "content", ref=ref, offset=1, limit=1)
        assert first["total"] == second["total"] == 2
        assert first["next_offset"] == 1 and second["next_offset"] is None
        passages = first["passages"] + second["passages"]
        assert [p["node"] for p in passages] == [7, 8]
        assert "".join(p["text"] for p in passages) == "In the gap and out."
        assert [t["node"] for p in passages for t in p["tokens"]] == [1, 2, 3, 4, 5]
        selected = read_archive(archive, "content", ref=passages[0]["ref"])
        assert [p["node"] for p in selected["passages"]] == [7]
        assert selected["passages"][0]["text"] == "In the gap "


def test_global_read_keeps_slots_outside_all_sections(tmp_path: Path) -> None:
    archive = corpus(tmp_path, ({1, 2}, {4, 5}), book_slots={1, 2, 4, 5})
    pages = [read_archive(archive, "content", offset=offset, limit=2) for offset in (0, 2, 4)]
    assert [p["total"] for p in pages] == [5, 5, 5]
    assert [p["next_offset"] for p in pages] == [2, 4, None]
    passages = [passage for page in pages for passage in page["passages"]]
    assert [p["node"] for p in passages] == [1, 2, 3, 4, 5]
    assert [t["node"] for p in passages for t in p["tokens"]] == [1, 2, 3, 4, 5]
    assert "".join(p["text"] for p in passages) == "In the gap and out."
    selected = read_archive(archive, "content", ref="Mini")
    assert [p["node"] for p in selected["passages"]] == [7, 8]
    assert [t["node"] for p in selected["passages"] for t in p["tokens"]] == [1, 2, 4, 5]


def test_no_sections_keeps_source_slots_outside_finest_nodes(tmp_path: Path) -> None:
    archive = corpus(tmp_path, ({1, 2}, {4, 5}), sections=False)
    page = read_archive(archive, "content")
    assert [p["node"] for p in page["passages"]] == [1, 2, 3, 4, 5]
    assert "".join(p["text"] for p in page["passages"]) == "In the gap and out."


def test_global_read_uses_nearest_complete_section_level(tmp_path: Path) -> None:
    archive = corpus(tmp_path, ({1, 2}, {4, 5}), chapters=True)
    page = read_archive(archive, "content")
    assert [p["node"] for p in page["passages"]] == [9, 10]
    assert "".join(p["text"] for p in page["passages"]) == "In the gap and out."
    selected = read_archive(archive, "content", ref=page["passages"][0]["ref"])
    assert [p["node"] for p in selected["passages"]] == [9]
    assert [t["node"] for t in selected["passages"][0]["tokens"]] == [1, 2, 3]
