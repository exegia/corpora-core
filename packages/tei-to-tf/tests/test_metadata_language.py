"""Independent metadata selection, explicit hints, source order and repair validation."""

import os
from pathlib import Path

import pytest
from test_quality import AI, Checker

from tei_to_tf.cli import main
from tei_to_tf.hosted_ai import suggest_spelling
from tei_to_tf.parse import secure_tree
from tei_to_tf.quality import SpellProcess, inspect_tree, text_segments

ENGLISH = "This edition was encoded by the library and published with a critical apparatus."
FRENCH = "Cette édition présente les poèmes et les notes de la bibliothèque française."
DUTCH = "Dit is een Nederlandse beschrijving zonder een beschikbaar woordenboek."


def document(header, body=FRENCH, header_attributes=""):
    return secure_tree(
        (
            f'<TEI xmlns="http://www.tei-c.org/ns/1.0" xml:lang="fr">'
            f"<teiHeader {header_attributes}><fileDesc>{header}</fileDesc></teiHeader>"
            f"<text><body><p>{body}</p></body></text></TEI>"
        ).encode()
    )


class LanguageChecker(Checker):
    def __init__(self):
        self.calls = []

    def detect(self, text, locale):
        if locale:
            selected = locale
            method = "hint"
        elif DUTCH in text:
            return dict(locale="nl", dictionary=None, method="statistical", confidence=1.0)
        elif ENGLISH in text:
            selected, method = "en-US", "statistical"
        elif FRENCH in text:
            selected, method = "fr-FR", "statistical"
        else:
            return dict(locale="und", dictionary=None, method="undetermined", confidence=None)
        dictionary = {
            "fr-FR": "fr_FR",
            "fr": "fr_FR",
            "en-US": "en_US",
            "en": "en_US",
            "fr-FR-1990": "fr_FR_90",
        }[selected]
        return dict(
            locale="fr-FR" if dictionary.startswith("fr_") else "en-US",
            dictionary=dictionary,
            method=method,
            confidence=None if locale else 1.0,
        )

    def check(self, text, role, locale):
        self.calls.append((text, role, locale))
        return super().check(text, role, locale)


def test_english_metadata_and_short_fields_use_metadata_only_context():
    checker = LanguageChecker()
    _, detection = inspect_tree(
        document(f"<p>{ENGLISH}</p><author>and</author>"), checker, "fr-FR", {}
    )
    assert (FRENCH, "corpus", "fr-FR") in checker.calls
    assert (ENGLISH, "metadata", "en-US") in checker.calls
    assert ("and", "metadata", "en-US") in checker.calls
    selections = detection["metadata_segments"]
    assert selections[0]["basis"] == "segment"
    assert selections[1]["basis"] == "metadata_context"
    assert detection["dictionary"] == "fr_FR"


def test_metadata_override_is_separate_and_preserves_reform_dictionary_for_repairs():
    tree = document('<author xml:lang="en">helllo</author>')
    checker = LanguageChecker()
    issues, _ = inspect_tree(tree, checker, "fr-FR", {"helllo": "hello"}, "fr-FR-1990")
    issue = issues[0]
    assert issue["language"]["dictionary"] == "fr_FR_90"
    assert issue["language_basis"] == "metadata_override"
    assert issue["locale_hint"] == "fr-FR-1990"
    suggest_spelling(tree, issues, checker, AI())
    assert issue["replacement"] == "hello"
    assert ("hello", "metadata", "fr-FR-1990") in checker.calls
    assert (FRENCH, "corpus", "fr-FR") in checker.calls
    assert not any(role == "metadata" and locale == "fr-FR" for _, role, locale in checker.calls)


def test_local_xml_language_wins_and_foreign_inline_runs_do_not_join():
    tree = document('<author xml:lang="en">hell<hi xml:lang="fr-FR-1990">bonjour</hi>lo</author>')
    checker = LanguageChecker()
    issues, detection = inspect_tree(tree, checker, "fr-FR", {})
    assert issues == []
    assert ("hell", "metadata", "en") in checker.calls
    assert ("bonjour", "metadata", "fr-FR-1990") in checker.calls
    assert ("lo", "metadata", "en") in checker.calls
    assert not any(text == "helllo" for text, _, _ in checker.calls)
    assert [s["basis"] for s in detection["metadata_segments"]] == ["xml_lang"] * 3
    fields = [(field, hint) for _, field, role, hint in text_segments(tree) if role == "metadata"]
    assert fields == [("text", "en"), ("text", "fr-FR-1990"), ("tail", "en")]


def test_empty_language_resets_parent_and_unknown_language_stays_blocking():
    tree = document('<author xml:lang="">Unknown</author>', header_attributes='xml:lang="en"')
    checker = LanguageChecker()
    issues, _ = inspect_tree(tree, checker, "fr-FR", {"Unknown": "hello"})
    assert len(issues) == 1
    issue = issues[0]
    assert issue["code"] == "language_unresolved"
    assert issue["blocking"] and issue["score"] == 90
    assert issue["replacement"] is None
    assert issue["language"]["dictionary"] is None
    assert not any(text == "Unknown" for text, _, _ in checker.calls)
    suggest_spelling(tree, issues, checker, AI())
    assert issue["ai_status"] == "language_unresolved"
    assert issue["replacement"] is None


def test_confident_unsupported_segment_does_not_fall_back_to_english_context():
    checker = LanguageChecker()
    issues, _ = inspect_tree(document(f"<p>{ENGLISH}</p><p>{DUTCH}</p>"), checker, "fr-FR", {})
    assert len(issues) == 1
    assert issues[0]["code"] == "language_unresolved"
    assert issues[0]["language"]["locale"] == "nl"
    assert not any(text == DUTCH for text, _, _ in checker.calls)


def test_collection_metadata_context_does_not_leak_between_members():
    first = (
        f"<TEI><teiHeader><p>{ENGLISH}</p><author>and</author></teiHeader>"
        f"<text><body><p>{FRENCH}</p></body></text></TEI>"
    )
    second = (
        f"<TEI><teiHeader><p>{FRENCH}</p><author>et</author></teiHeader>"
        f"<text><body><p>{FRENCH}</p></body></text></TEI>"
    )
    tree = secure_tree(
        (f'<teiCorpus xmlns="http://www.tei-c.org/ns/1.0">{first}{second}</teiCorpus>').encode()
    )
    checker = LanguageChecker()
    inspect_tree(tree, checker, "fr-FR", {})
    assert ("and", "metadata", "en-US") in checker.calls
    assert ("et", "metadata", "fr-FR") in checker.calls


def test_metadata_locale_requires_quality_mode(tmp_path, capsys):
    assert (
        main(["source.xml", "--output", str(tmp_path / "out"), "--metadata-locale", "en-US"]) == 2
    )
    assert "Quality options require --quality-engine" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()


@pytest.mark.skipif(
    not os.environ.get("CORPORA_TEXT_CHECK") or not os.environ.get("CSPELL_DICTIONARIES"),
    reason="Requires native language engine and installed dictionaries",
)
def test_real_engine_checks_english_metadata_under_french_corpus_policy():
    checker = SpellProcess(
        Path(os.environ["CORPORA_TEXT_CHECK"]), Path(os.environ["CSPELL_DICTIONARIES"])
    )
    try:
        issues, evidence = inspect_tree(
            document(f"<p>{ENGLISH}</p><author>and</author>"), checker, "fr-FR", {}
        )
        assert evidence["dictionary"] == "fr_FR"
        assert {s["language"]["dictionary"] for s in evidence["metadata_segments"]} == {"en_US"}
        assert not any(d["blocking"] for d in issues if d["role"] == "metadata")
    finally:
        checker.close()
