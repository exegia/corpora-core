"""Offline oracle tests plus opt-in regression against the exact public-source bytes."""

import copy
import os
from pathlib import Path

import pytest
from tf.fabric import Fabric

from tei_to_tf import ConversionError, convert
from tei_to_tf.model import Source
from tei_to_tf.qa_baudelaire import page, run, source_view, verify_projection


def corpus(tmp_path):
    data = (
        b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><teiHeader/><text><body>'
        b'<div><head>Title</head><lg n="1" subtype="couplet">'
        b'<l n="1">A &amp; B</l><l n="2">C</l></lg></div></body></text></TEI>'
    )
    convert([], tmp_path / "out", sources=[Source("test.xml", "file:///test.xml", data)])
    api = Fabric(locations=str(tmp_path / "out/tf"), silent="deep").load(
        "text tei_tag attributes start end parent document region block", silent="deep"
    )
    return api, source_view(data)


def test_independent_source_and_tf_oracles(tmp_path):
    api, expected = corpus(tmp_path)
    proof = verify_projection(api, expected)
    assert proof["lines"] == 2
    assert proof["stanzas"] == 1
    assert proof["empty_slots"] == 0


def test_oracle_detects_changed_verse(tmp_path):
    api, expected = corpus(tmp_path)
    altered = copy.deepcopy(expected)
    altered["stanzas"][0]["lines"][0]["text"] = "different"
    with pytest.raises(ConversionError, match="differs from independent TEI"):
        verify_projection(api, altered)


def test_oracle_detects_broken_stanza_membership(tmp_path, monkeypatch):
    api, expected = corpus(tmp_path)
    monkeypatch.setattr(api.E.parent, "f", lambda _: ())
    with pytest.raises(ConversionError, match="differs from independent TEI"):
        verify_projection(api, expected)


def test_html_escapes_corpus_content(tmp_path):
    api, view = corpus(tmp_path)
    proof = verify_projection(api, view)
    view["stanzas"][0]["lines"][0]["text"] = '<script>alert("bad")</script>'
    output = page(view, "tf", proof)
    assert "<script>" not in output
    assert "&lt;script&gt;" in output


@pytest.mark.skipif(
    not os.environ.get("BAUDELAIRE_SOURCE") or not os.environ.get("TF_VALIDATOR"),
    reason="Set BAUDELAIRE_SOURCE and TF_VALIDATOR for pinned full QA regression",
)
def test_pinned_baudelaire_conversion_and_validation(tmp_path):
    validator = Path(os.environ["TF_VALIDATOR"]) / "scripts/tf_validate.py"
    result = run(tmp_path / "output", validator, Path(os.environ["BAUDELAIRE_SOURCE"]))
    assert result["status"] == "passed-with-proven-whitespace-exception"
    assert result["loaders"]["text-fabric-warm"]["characters"] == 904
    assert result["loaders"]["context-fabric-warm"]["lines"] == 14
    assert (tmp_path / "output/browser/tei.html").is_file()
    assert (tmp_path / "output/browser/tf.html").is_file()
