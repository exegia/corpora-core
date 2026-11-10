"""Build a static, local PDF and extraction comparison site."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).parent


def build(pdf: Path, site: Path, languages: str) -> None:
    pdf = pdf.resolve(strict=True)
    site.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["cargo", "run", "--quiet", "-p", "corpora-pdf", "--example", "qa_export", "--", str(pdf), languages],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    extraction = json.loads(result.stdout)
    (site / "result.json").write_text(json.dumps(extraction, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    review = {
        "source_name": pdf.name,
        "units": [
            {
                "label": f"Page {page['number']}",
                "source_url": f"source.pdf#page={page['number']}&toolbar=0",
                "summary": (
                    f"{page['method'].replace('_', ' ')} · language: "
                    f"{page['language'] or 'unknown'}"
                    f"{' (uncertain)' if not page['language_reliable'] else ''}"
                ),
                "score": page["extraction_score"],
                "findings": [
                    finding
                    for finding in extraction["findings"] + extraction.get("script_review", [])
                    if finding["page"] in (None, page["number"])
                ],
                "elements": page["elements"],
            }
            for page in extraction["pages"]
        ],
    }
    (site / "review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copy2(pdf, site / "source.pdf")
    for name in ("index.html", "review.css", "review.js"):
        shutil.copy2(ASSETS / name, site / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("site", type=Path)
    parser.add_argument("--languages", default="eng", help="installed Tesseract codes, e.g. eng+fra")
    args = parser.parse_args()
    build(args.pdf, args.site, args.languages)
    print(f"Review site: {args.site / 'index.html'}")
    print(f"Serve it: python3 -m http.server 8771 --bind 127.0.0.1 -d {args.site}")


if __name__ == "__main__":
    main()
