"""CLI for pinned TF selections and audited AI resolution overlays."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from .api import CodexExpert, ResolveError, Selection, inspect_selection, resolve


def _request(path: Path) -> tuple[Selection, str, str]:
    data: Any = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"selection", "mode", "prompt"}:
        raise ResolveError("Request needs selection, mode, and prompt")
    if not isinstance(data["selection"], dict):
        raise ResolveError("Selection must be an object")
    try:
        selection = Selection(**data["selection"])
    except TypeError as error:
        raise ResolveError("Selection fields are invalid") from error
    if not isinstance(data["mode"], str) or not isinstance(data["prompt"], str):
        raise ResolveError("Mode and prompt must be strings")
    return selection, data["mode"], data["prompt"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Pin an exact Unicode-scalar TF selection")
    inspect.add_argument("tf_dir", type=Path)
    inspect.add_argument("node", type=int)
    inspect.add_argument("start", type=int)
    inspect.add_argument("end", type=int)
    inspect.add_argument("--text-feature", required=True)
    inspect.add_argument("--text-format")
    run = commands.add_parser("resolve", help="Run the expert and stage a TF annotation overlay")
    run.add_argument("tf_dir", type=Path)
    run.add_argument("request", type=Path, help="JSON with selection, mode, and prompt")
    run.add_argument("output", type=Path, help="New output directory")
    run.add_argument("--expert-instructions", type=Path)
    run.add_argument("--codex-command", default="codex")
    run.add_argument("--model")
    args = parser.parse_args()
    try:
        if args.command == "inspect":
            selection = inspect_selection(
                args.tf_dir, args.node, args.start, args.end, args.text_feature, args.text_format
            )
            print(json.dumps(asdict(selection), ensure_ascii=False, sort_keys=True))
            return
        instructions = args.expert_instructions or (
            Path(__file__).resolve().parents[4] / "agent/text-fabric-expert/SYSTEM.md"
        )
        selection, mode, prompt = _request(args.request)
        report = resolve(
            args.tf_dir,
            args.output,
            selection,
            mode,
            prompt,
            CodexExpert(instructions, args.codex_command, args.model),
        )
        print(
            json.dumps(
                {
                    "output": str(args.output.resolve()),
                    "resolution_id": report["resolution"]["id"],
                    "status": report["resolution"]["status"],
                },
                sort_keys=True,
            )
        )
    except (OSError, ValueError) as error:
        parser.exit(2, f"tf-ai-resolver: {error}\n")


if __name__ == "__main__":
    main()
