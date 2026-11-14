"""Command line entry point."""

import argparse
import json
import sys
from pathlib import Path

import httpx
from lxml import etree

from .acquire import Limits
from .convert import convert
from .hosted_ai import HostedAI
from .model import ConversionError, Policy
from .quality import SpellProcess, quality_convert


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert TEI files/directories/HTTPS repositories to TF"
    )
    parser.add_argument(
        "sources", nargs="+", help="Local paths, direct HTTPS, GitHub or HF repo URLs"
    )
    parser.add_argument("--output", type=Path, required=True, help="New output directory")
    parser.add_argument(
        "--revision", help="Repository branch/tag/commit; resolved to immutable commit"
    )
    parser.add_argument("--choice", choices=["reject", "original", "edited"], default="reject")
    parser.add_argument("--apparatus", choices=["reject", "lemma", "witness"], default="reject")
    parser.add_argument("--witness", help="Exact witness token, e.g. '#A'")
    parser.add_argument("--notes", choices=["separate", "include"], default="separate")
    parser.add_argument("--allow-no-namespace", action="store_true")
    parser.add_argument(
        "--milestones",
        choices=["offsets", "pages"],
        default="offsets",
        help="pages: project each TEI pb up to the next pb as a TF page node",
    )
    parser.add_argument(
        "--facsimile",
        choices=["ignore", "zones"],
        default="ignore",
        help="zones: resolve @facs to integer facsimile zone coordinate features",
    )
    parser.add_argument("--max-slots", type=int, default=1_000_000)
    parser.add_argument("--max-memberships", type=int, default=10_000_000)
    parser.add_argument("--schema", type=Path, help="Optional local self-contained RNG or XSD")
    parser.add_argument("--max-files", type=int, default=1000)
    parser.add_argument("--max-file-bytes", type=int, default=64 * 1024 * 1024)
    parser.add_argument("--max-total-bytes", type=int, default=256 * 1024 * 1024)
    parser.add_argument(
        "--quality-engine", type=Path, help="corpora-text-check executable; enables three-pass QA"
    )
    parser.add_argument("--dictionaries", type=Path, help="Installed cspell dictionary directory")
    parser.add_argument(
        "--locale",
        help="Corpus language/orthography hint, e.g. grc or fr-FR-1990; "
        "metadata is selected independently",
    )
    parser.add_argument("--metadata-locale", help="Explicit metadata language/orthography override")
    parser.add_argument(
        "--corrections", type=Path, help="JSON word-to-replacement map for non-corpus text"
    )
    parser.add_argument(
        "--ai-bridge", type=Path, help="Path to built quality-ai/dist/bridge.js; enables hosted AI"
    )
    parser.add_argument("--ai-model", default="google/gemini-3.5-flash-lite")
    parser.add_argument("--ai-max-requests", type=int, default=100)
    parser.add_argument("--repair-cycles", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if args.quality_engine:
            if not args.dictionaries:
                raise ConversionError("--quality-engine requires --dictionaries")
            checker = SpellProcess(args.quality_engine, args.dictionaries)
            try:
                corrections = json.loads(args.corrections.read_text()) if args.corrections else {}
                if not isinstance(corrections, dict) or not all(
                    isinstance(k, str) and isinstance(v, str) and v.strip()
                    for k, v in corrections.items()
                ):
                    raise ConversionError("Corrections must map words to nonempty strings")
                result = quality_convert(
                    args.sources,
                    args.output,
                    checker,
                    Policy(
                        args.choice,
                        args.apparatus,
                        args.witness,
                        args.notes,
                        args.allow_no_namespace,
                        args.max_slots,
                        args.max_memberships,
                        args.milestones,
                        args.facsimile,
                    ),
                    args.locale,
                    corrections,
                    args.revision,
                    args.schema,
                    limits=Limits(args.max_files, args.max_file_bytes, args.max_total_bytes),
                    ai=HostedAI(args.ai_bridge, args.ai_model, args.ai_max_requests)
                    if args.ai_bridge
                    else None,
                    max_cycles=args.repair_cycles,
                    metadata_locale=args.metadata_locale,
                )
                print(
                    json.dumps(
                        {
                            "status": result["status"],
                            "passed": result["passed"],
                            "blocked": result["blocked"],
                            "report": str(args.output / "quality-report.json"),
                        }
                    )
                )
                return 0 if result["status"] == "passed" else 1
            finally:
                checker.close()
        if (
            args.dictionaries
            or args.locale
            or args.metadata_locale
            or args.corrections
            or args.ai_bridge
        ):
            raise ConversionError("Quality options require --quality-engine")
        result = convert(
            args.sources,
            args.output,
            Policy(
                args.choice,
                args.apparatus,
                args.witness,
                args.notes,
                args.allow_no_namespace,
                args.max_slots,
                args.max_memberships,
                args.milestones,
                args.facsimile,
            ),
            Limits(args.max_files, args.max_file_bytes, args.max_total_bytes),
            args.revision,
            args.schema,
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "documents": len(result["documents"]),
                    "slots": result["graph"]["max_slot"],
                    "status": "converted",
                }
            )
        )
        return 0
    except (
        ConversionError,
        OSError,
        httpx.HTTPError,
        etree.LxmlError,
        KeyError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
