"""Build a static, local PDF and extraction comparison site."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ASSETS = Path(__file__).parent
PDF_TO_TF = ROOT / "packages/pdf-to-tf"
# Runs pdf-to-tf's own TEI builder on this extraction, so line ids match the cards.
TEI_SCRIPT = (
    "import json, sys; from pdf_to_tf.tei import build_tei; "
    "data = json.load(open(sys.argv[1], encoding='utf-8')); "
    "open(sys.argv[2], 'wb').write(build_tei(data, sys.argv[3], {}).xml)"
)


def render_page(pdf: Path, site: Path, number: int) -> str:
    """Render at the extraction coordinate scale; no browser PDF plugin needed."""
    name = f"source-page-{number}"
    subprocess.run(
        ["pdftoppm", "-f", str(number), "-l", str(number), "-singlefile",
         "-r", "108", "-png", str(pdf), str(site / name)],
        capture_output=True, check=True,
    )
    if not (site / f"{name}.png").is_file():
        raise RuntimeError(f"Source rendering missing for page {number}")
    return f"{name}.png"


def write_tei(site: Path, title: str) -> str:
    """Write document.tei.xml as pdf-to-tf would build it from result.json."""
    subprocess.run(
        ["uv", "run", "--quiet", "--project", str(PDF_TO_TF), "python", "-c", TEI_SCRIPT,
         str(site / "result.json"), str(site / "document.tei.xml"), title],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return "document.tei.xml"


def build(pdf: Path, site: Path, languages: str, tei: bool = True) -> None:
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
        "tei_url": write_tei(site, pdf.stem) if tei else None,
        "units": [
            {
                "label": f"Page {page['number']}",
                "source_url": f"source.pdf#page={page['number']}&toolbar=0",
                "source_image_url": render_page(pdf, site, page["number"]),
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
    # Version the assets by content so a reload after a rebuild never runs stale code.
    page = (ASSETS / "index.html").read_text(encoding="utf-8")
    for name in ("review.css", "review.js"):
        shutil.copy2(ASSETS / name, site / name)
        digest = hashlib.sha256((ASSETS / name).read_bytes()).hexdigest()[:12]
        page = page.replace(f'"{name}"', f'"{name}?v={digest}"')
    (site / "index.html").write_text(page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("site", type=Path)
    parser.add_argument("--languages", default="eng", help="installed Tesseract codes, e.g. eng+fra")
    parser.add_argument("--no-tei", action="store_true", help="skip the TEI column (needs uv and packages/pdf-to-tf)")
    args = parser.parse_args()
    build(args.pdf, args.site, args.languages, tei=not args.no_tei)
    print(f"Review site: {args.site / 'index.html'}")
    print(f"Serve it: python3 -m http.server 8771 --bind 127.0.0.1 -d {args.site}")


if __name__ == "__main__":
    main()
