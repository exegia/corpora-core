"""pdf-to-tf command line."""

import argparse
import json
import sys
from pathlib import Path

from lxml import etree
from tei_to_tf import ConversionError

from .gate import DEFAULT_MIN_SCORE
from .pipeline import ConversionFailed, convert

EXIT = {"converted": 0, "converted_with_issues": 0, "verification_failed": 1, "gated": 3}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdf-to-tf",
        description="Extract a PDF, gate on its score, then convert PDF → TEI → Text-Fabric.",
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    parser.add_argument(
        "--extractor",
        default="corpora-pdf-extract",
        help="path to the corpora-pdf-extract binary "
        "(cargo build -p corpora-pdf --bin corpora-pdf-extract)",
    )
    parser.add_argument("--languages", default="eng", help="Tesseract languages, e.g. eng+heb")
    parser.add_argument("--tessdata", type=Path, help="directory of .traineddata models")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument(
        "--no-visual-check",
        action="store_true",
        help="skip OCR of text-layer pages; their text then scores 0 and the gate fails",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=DEFAULT_MIN_SCORE,
        help="convert only when the score is greater than this (default 0.95)",
    )
    parser.add_argument("--schema", type=Path, help="local self-contained RNG/XSD for the TEI")
    args = parser.parse_args(argv)
    try:
        report = convert(
            args.pdf,
            args.output,
            extractor=args.extractor,
            languages=args.languages,
            tessdata=args.tessdata,
            max_pages=args.max_pages,
            visual_check=not args.no_visual_check,
            min_score=args.min_score,
            schema=args.schema,
        )
    except (ConversionFailed, ConversionError, OSError, ValueError, etree.LxmlError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "score": round(report["gate"]["score"], 4),
                "issues": report["issue_counts"],
                "report": str(args.output / "conversion-report.md"),
            }
        )
    )
    return EXIT[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
