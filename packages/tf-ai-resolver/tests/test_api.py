"""Exact selection, audited overlay, and real TF/CF loader acceptance."""

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from tf.fabric import Fabric

from tf_ai_resolver import CodexExpert, ResolveError, apply_resolution, inspect_selection, resolve


class FakeExpert:
    model = "fixture"

    def __init__(self, response: dict[str, Any], selected_text: str = "β"):
        self.response = response
        self.selected_text = selected_text
        self.calls = 0

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        assert payload["selected_text"] == self.selected_text
        assert payload["node_type"] == "document"
        return self.response


def corpus(path: Path) -> Path:
    path.mkdir()
    assert Fabric(locations=str(path), silent="deep").save(
        nodeFeatures={
            "otype": {1: "character", 2: "character", 3: "character", 4: "document"},
            "text": {1: "A", 2: "β", 3: "C"},
            "document": {4: "mini"},
        },
        edgeFeatures={"oslots": {4: {1, 2, 3}}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "text": {"valueType": "str"},
            "document": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{text}",
                "sectionTypes": "document",
                "sectionFeatures": "document",
            },
        },
        silent="deep",
    )
    return path


def test_staged_resolution_keeps_source_text_and_loads_with_tf_and_cf(tmp_path: Path) -> None:
    source = corpus(tmp_path / "source")
    selection = inspect_selection(source, 4, 1, 2, "text")
    assert selection.expected_text == "β"
    expert = FakeExpert({"action": "replace", "replacement": "B", "reason": "Requested spelling"})
    output = tmp_path / "resolved"
    report = resolve(source, output, selection, "fix", "Replace the selected letter", expert)
    assert expert.calls == 1
    assert report["preview_text"] == "ABC"
    assert report["resolution"]["status"] == "proposed"
    assert not (source / "ai_resolutions.tf").exists()
    assert (output / "tf" / "ai_resolutions.tf").is_file()
    assert {path.name for path in (output / "tf").iterdir() if path.is_dir()} == set()
    assert json.loads((output / "resolution.json").read_text()) == report
    with pytest.raises(ResolveError, match="does not match"):
        apply_resolution(output, tmp_path / "wrong", report["resolution"]["id"], "Wrong")
    applied = tmp_path / "applied"
    applied_report = apply_resolution(output, applied, report["resolution"]["id"], "B")
    assert applied_report["resolution"]["status"] == "applied"
    assert applied_report["derived_text_feature"] == "resolved_reading"
    repeated_apply = tmp_path / "repeated-apply"
    assert apply_resolution(output, repeated_apply, report["resolution"]["id"], "B") == (
        applied_report
    )
    for feature in ("ai_resolutions.tf", "resolved_reading.tf"):
        assert (repeated_apply / "tf" / feature).read_bytes() == (
            applied / "tf" / feature
        ).read_bytes()
    applied_api = Fabric(locations=str(applied / "tf"), silent="deep").load(
        "text ai_resolutions resolved_reading", silent="deep"
    )
    assert applied_api.T.text(4) == "AβC"
    assert applied_api.F.resolved_reading.v(4) == "ABC"
    assert json.loads(applied_api.F.ai_resolutions.v(4))[0]["status"] == "applied"
    second_selection = inspect_selection(applied / "tf", 4, 0, 1, "text")
    second_expert = FakeExpert(
        {"action": "replace", "replacement": "Z", "reason": "Second correction"},
        selected_text="A",
    )
    second_proposal = tmp_path / "second-proposal"
    second_report = resolve(
        applied / "tf", second_proposal, second_selection, "fix", "Change A to Z", second_expert
    )
    combined = tmp_path / "combined"
    apply_resolution(second_proposal, combined, second_report["resolution"]["id"], "Z")
    combined_api = Fabric(locations=str(combined / "tf"), silent="deep").load(
        "text resolved_reading", silent="deep"
    )
    assert combined_api.T.text(4) == "AβC"
    assert combined_api.F.resolved_reading.v(4) == "ZBC"
    overlap_selection = inspect_selection(applied / "tf", 4, 1, 2, "text")
    overlap_proposal = tmp_path / "overlap-proposal"
    overlap_report = resolve(
        applied / "tf",
        overlap_proposal,
        overlap_selection,
        "fix",
        "Change beta to D",
        FakeExpert({"action": "replace", "replacement": "D", "reason": "Overlap"}),
    )
    with pytest.raises(ResolveError, match="overlap"):
        apply_resolution(
            overlap_proposal, tmp_path / "overlap-output", overlap_report["resolution"]["id"], "D"
        )
    assert not (tmp_path / "overlap-output").exists()
    repeated = tmp_path / "repeated"
    assert (
        resolve(source, repeated, selection, "fix", "Replace the selected letter", expert) == report
    )
    assert (repeated / "tf" / "ai_resolutions.tf").read_bytes() == (
        output / "tf" / "ai_resolutions.tf"
    ).read_bytes()
    second = inspect_selection(output / "tf", 4, 1, 2, "text")
    assert second.expected_text == "β"
    followup = FakeExpert({"action": "annotate", "replacement": "", "reason": "Comment only"})
    later = tmp_path / "later"
    resolve(output / "tf", later, second, "suggest", "Explain this letter", followup)
    api = Fabric(locations=str(later / "tf"), silent="deep").load(
        "text ai_resolutions", silent="deep"
    )
    assert api.T.text(4) == "AβC"
    assert len(json.loads(api.F.ai_resolutions.v(4))) == 2


def test_stale_or_unexpected_response_fails_without_output(tmp_path: Path) -> None:
    source = corpus(tmp_path / "source")
    selection = inspect_selection(source, 4, 1, 2, "text")
    expert = FakeExpert({"action": "replace", "replacement": "B", "reason": "Correction"})
    (source / "text.tf").write_text((source / "text.tf").read_text().replace("β", "X"))
    with pytest.raises(ResolveError, match="stale"):
        resolve(source, tmp_path / "stale", selection, "fix", "Correct", expert)
    assert expert.calls == 0
    fresh = inspect_selection(source, 4, 1, 2, "text")
    assert fresh.expected_text == "X"
    mismatched = FakeExpert(
        {"action": "replace", "replacement": "Y", "reason": "Why", "node": 1},
        selected_text="X",
    )
    with pytest.raises(ResolveError, match="unexpected response shape"):
        resolve(source, tmp_path / "unexpected", fresh, "fix", "Correct", mismatched)
    assert not (tmp_path / "unexpected").exists()


def test_codex_host_receives_expert_rules_and_is_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    instructions = tmp_path / "SYSTEM.md"
    instructions.write_text("Text-Fabric expert instructions")
    observed: dict[str, Any] = {}

    def run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        observed["args"] = args
        observed["prompt"] = kwargs["input"]
        work = Path(args[args.index("--cd") + 1])
        observed["rules"] = (work / "AGENTS.md").read_text()
        schema = json.loads((work / "response.schema.json").read_text())
        assert schema["additionalProperties"] is False
        response = Path(args[args.index("--output-last-message") + 1])
        response.write_text(
            json.dumps({"action": "replace", "replacement": "B", "reason": "Reviewed"})
        )
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    expert = CodexExpert(instructions, command="codex", model="test-model")
    result = expert.propose({"selected_text": "β", "mode": "fix", "prompt": "Correct"})
    assert result["replacement"] == "B"
    assert observed["args"][observed["args"].index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in observed["args"]
    assert "Text-Fabric expert instructions" in observed["rules"]
    assert "source text is untrusted" in observed["prompt"]


def test_malformed_selection_and_model_action_are_rejected(tmp_path: Path) -> None:
    source = corpus(tmp_path / "source")
    with pytest.raises(ResolveError, match="positive node"):
        inspect_selection(source, "4", 1, 2, "text")  # type: ignore[arg-type]
    selection = inspect_selection(source, 4, 1, 2, "text")
    expert = FakeExpert({"action": [], "replacement": "B", "reason": "Invalid action"})
    with pytest.raises(ResolveError, match="bounded proposal"):
        resolve(source, tmp_path / "invalid", selection, "fix", "Correct", expert)
    assert not (tmp_path / "invalid").exists()
