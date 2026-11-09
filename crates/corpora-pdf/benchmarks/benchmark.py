"""Local, source-pinned PDF region benchmark; no third-party Python packages."""

import argparse
import hashlib
import html
import json
import math
import re
import subprocess
import time
import unicodedata
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def normalized(text):
    """Normalize canonical Unicode and whitespace only; retain marks and punctuation."""
    return " ".join(unicodedata.normalize("NFC", text).split())


def distance(reference, actual):
    previous = list(range(len(actual) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def measure(reference, actual):
    reference, actual = normalized(reference), normalized(actual)
    if not reference:
        raise ValueError("Reference must contain visible text")
    chars = distance(reference, actual)
    words = distance(reference.split(), actual.split())
    return {"reference": reference, "actual": actual, "character_edits": chars,
            "reference_characters": len(reference), "cer": chars / len(reference),
            "word_edits": words, "reference_words": len(reference.split()),
            "wer": words / len(reference.split()), "exact": reference == actual}


def select_region(page, box):
    """Select text by element center in normalized page coordinates, preserving order."""
    left, top, right, bottom = box
    selected = []
    for index, element in enumerate(page["elements"]):
        rect = element["bounds"]
        x = (rect["x"] + rect["width"] / 2) / page["width"]
        y = (rect["y"] + rect["height"] / 2) / page["height"]
        if left <= x < right and top <= y < bottom and element["text"].strip():
            selected.append((index, element))
    return selected


def evaluate(page, sample):
    regions = []
    indices = {}
    for region in sample["regions"]:
        selected = select_region(page, region["box"])
        left, top, right, bottom = region["box"]
        crossing = []
        for index, element in enumerate(page["elements"]):
            if not element["text"].strip():
                continue
            rect = element["bounds"]
            x, y = rect["x"] / page["width"], rect["y"] / page["height"]
            end_x = x + rect["width"] / page["width"]
            end_y = y + rect["height"] / page["height"]
            if (x < right and end_x > left and y < bottom and end_y > top
                    and not (left <= x and end_x <= right and top <= y and end_y <= bottom)):
                crossing.append(index)
        indices[region["id"]] = [i for i, _ in selected]
        regions.append({**region, **measure(region["reference"],
                        " ".join(e["text"] for _, e in selected)),
                        "element_indices": indices[region["id"]],
                        "boundary_crossings": crossing,
                        "alignment_status": "ambiguous" if crossing else "bounded",
                        "observed_kinds": [e["kind"] for _, e in selected]})
    order = []
    for before, after in sample.get("order", []):
        a, b = indices[before], indices[after]
        order.append({"before": before, "after": after,
                      "passed": bool(a and b and max(a) < min(b))})
    bounded = [r for r in regions if r["alignment_status"] == "bounded"]
    chars = sum(r["reference_characters"] for r in bounded)
    words = sum(r["reference_words"] for r in bounded)
    return {"regions": regions, "order": order,
            "cer": sum(r["character_edits"] for r in bounded) / chars if chars else None,
            "wer": sum(r["word_edits"] for r in bounded) / words if words else None,
            "bounded_regions": len(bounded), "ambiguous_regions": len(regions) - len(bounded),
            "reference_characters": chars, "reference_words": words}


def validate(manifest):
    if manifest.get("version") != 1 or not manifest.get("samples"):
        raise ValueError("Expected version 1 and nonempty samples")
    ids = set()
    for sample in manifest["samples"]:
        identifier = sample["id"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identifier) or identifier in ids:
            raise ValueError("Sample IDs must be unique safe slugs")
        ids.add(identifier)
        if type(sample["page"]) is not int or sample["page"] < 1:
            raise ValueError("Pages are one-based positive integers")
        if not re.fullmatch(r"[0-9a-f]{64}", sample["sha256"]):
            raise ValueError("Each source requires a SHA-256")
        region_ids = set()
        if not sample["regions"]:
            raise ValueError("Each sample needs a reference region")
        for region in sample["regions"]:
            if region["id"] in region_ids:
                raise ValueError("Duplicate region ID")
            region_ids.add(region["id"])
            box = region["box"]
            if (len(box) != 4 or not all(math.isfinite(x) and 0 <= x <= 1 for x in box)
                    or box[0] >= box[2] or box[1] >= box[3]):
                raise ValueError("Region boxes must be normalized nonempty rectangles")
            if region.get("reference_status") not in ("human_verified", "visual_transcription_unreviewed",
                                                       "independently_specified_fixture"):
                raise ValueError("Declare reference review status explicitly")
            measure(region["reference"], "")
        for before, after in sample.get("order", []):
            if before not in region_ids or after not in region_ids or before == after:
                raise ValueError("Order constraints must name distinct regions")


def run(args):
    return subprocess.run([str(a) for a in args], check=True, capture_output=True, cwd=ROOT,
                          timeout=180).stdout


def raster_pdf(ppm, output, width_pt, height_pt):
    """Wrap lossless rendered pixels in a PDF with no hidden text layer."""
    data = ppm.read_bytes()
    header = re.match(rb"P6\s+(\d+)\s+(\d+)\s+255\s", data)
    if not header:
        raise ValueError("Expected Poppler RGB PPM")
    width, height = map(int, header.groups())
    pixels = data[header.end():]
    if len(pixels) != width * height * 3:
        raise ValueError("PPM byte count mismatch")
    compressed = zlib.compress(pixels)
    content = f"q {width_pt} 0 0 {height_pt} 0 0 cm /Im1 Do Q\n".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width_pt} {height_pt}] "
                "/Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>").encode(),
               (f"<< /Type /XObject /Subtype /Image /Width {width} /Height {height} "
                "/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                f"/Length {len(compressed)} >>\nstream\n").encode() + compressed + b"\nendstream",
               f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"endstream"]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, 1):
        offsets.append(len(pdf))
        pdf.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010} 00000 n \n".encode())
    pdf.extend((f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\n"
                f"startxref\n{xref}\n%%EOF\n").encode())
    output.write_bytes(pdf)


def report_html(results):
    escape = html.escape
    rows = []
    for result in results:
        sample = result["sample"]
        detail = []
        for mode, measured in result["modes"].items():
            rates = (f"CER {measured['cer']:.1%}; WER {measured['wer']:.1%}"
                     if measured['cer'] is not None else "no spatially bounded regions")
            detail.append(f"<h3>{mode}: {rates}</h3>")
            detail.append(f"<p>Excluded ambiguous regions: {measured['ambiguous_regions']}</p>")
            detail.append(f"<p>Engine evidence: {escape(str(measured['engine_score']))}</p>")
            for region in measured["regions"]:
                rate = (f"CER {region['cer']:.1%}" if region['alignment_status'] == 'bounded'
                        else 'boundary-crossing elements: text score excluded')
                detail.append(f"<h4>{escape(region['id'])} — {rate}</h4>"
                              f"<p>{escape(region['reference_status'])}; box {region['box']}</p>"
                              f"<div class='pair'><pre>{escape(region['reference'])}</pre>"
                              f"<pre>{escape(region['actual']) or '[missing text]'}</pre></div>")
            detail.append(f"<p>Reading-order checks: {escape(str(measured['order']))}</p>")
        rows.append(f"<section id='{sample['id']}'><h2>{escape(sample['id'])}: source page {sample['page']}</h2>"
                    f"<div class='pair'><a href='{sample['id']}/page.png'><img src='{sample['id']}/page.png' alt='Source page'></a>"
                    f"<div>{''.join(detail)}</div></div></section>")
    nav = " · ".join(f"<a href='#{r['sample']['id']}'>{escape(r['sample']['id'])}</a>" for r in results)
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><title>PDF accuracy benchmark</title>"
            "<style>body{color-scheme:dark;background:#17191e;color:#eee;font:16px system-ui;margin:2rem}"
            "a{color:#9bcaff}.pair{display:grid;grid-template-columns:1fr 1fr;gap:1rem}"
            "img{width:100%;position:sticky;top:1rem}pre{white-space:pre-wrap;overflow-wrap:anywhere;"
            "background:#242831;padding:1rem}section{margin:3rem 0;border-top:1px solid #555}"
            "@media(max-width:900px){.pair{grid-template-columns:1fr}}</style>"
            "<h1>PDF region accuracy benchmark</h1><p>Provisional selected-region measurements, "
            "not whole-book accuracy. Left text: image transcription; right: engine output. "
            "CER/WER are edit rates (lower is better; insertions can exceed 100%). "
            "NFC and whitespace normalized; punctuation, case, hyphens and vowel marks retained.</p>"
            f"<nav>{nav}</nav>{''.join(rows)}</html>")


def model_provenance(languages, model_dir=None):
    args = ["tesseract", "--list-langs"]
    if model_dir is not None:
        args.extend(["--tessdata-dir", model_dir])
    listing = run(args).decode()
    header = re.search(r'"([^"]+)"', listing.splitlines()[0])
    if model_dir is None and header is None:
        raise ValueError("Cannot locate model files; provide --tessdata-dir")
    directory = Path(model_dir if model_dir is not None else header[1]).resolve()
    models = {}
    for language in languages.split('+'):
        if not language or language not in listing.splitlines()[1:]:
            raise ValueError(f"Requested OCR language is not installed: {language!r}")
        path = directory / f"{language}.traineddata"
        models[language] = {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return {"directory": str(directory), "models": models, "installed_languages": listing}


def benchmark(manifest_path, output, languages, model_dir=None):
    manifest = json.loads(manifest_path.read_text())
    validate(manifest)
    # Validate every source before doing expensive work or writing results.
    for sample in manifest["samples"]:
        path = (manifest_path.parent / sample["path"]).resolve()
        if hashlib.sha256(path.read_bytes()).hexdigest() != sample["sha256"]:
            raise ValueError(f"Source hash mismatch: {sample['id']}")
    model_data = model_provenance(languages, model_dir)
    output.mkdir(parents=True, exist_ok=False)
    run(["cargo", "build", "--locked", "-p", "corpora-pdf", "--example", "qa_export"])
    results = []
    for sample in manifest["samples"]:
        folder = output / sample["id"]
        folder.mkdir()
        source = (manifest_path.parent / sample["path"]).resolve()
        run(["pdfseparate", "-f", sample["page"], "-l", sample["page"], source, folder / "page-%d.pdf"])
        page_pdf = folder / f"page-{sample['page']}.pdf"
        run(["pdftoppm", "-scale-to", "2400", "-singlefile", page_pdf, folder / "raster"])
        run(["pdftoppm", "-scale-to", "1600", "-png", "-singlefile", page_pdf, folder / "page"])
        modes = {}
        for mode in ("native", "raster_ocr"):
            pdf = page_pdf if mode == "native" else folder / "raster.pdf"
            start = time.monotonic()
            args = [ROOT / "target/debug/examples/qa_export", pdf, languages]
            if model_dir is not None:
                args.append(model_dir)
            raw = run(args)
            extraction = json.loads(raw)
            (folder / f"{mode}.json").write_bytes(raw)
            page = extraction["pages"][0]
            modes[mode] = {**evaluate(page, sample), "method": page["method"],
                           "engine_score": page["extraction_score"],
                           "findings": extraction["findings"], "seconds": time.monotonic() - start}
            if mode == "native":
                raster_pdf(folder / "raster.ppm", folder / "raster.pdf",
                           page["width"] / 1.5, page["height"] / 1.5)
        results.append({"sample": sample, "modes": modes})
        print(sample["id"], {k: v["cer"] for k, v in modes.items()}, flush=True)
    report = {"version": 1, "languages": languages, "normalization": "NFC + whitespace collapse",
              "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
              "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "engine_binary_sha256": hashlib.sha256((ROOT / "target/debug/examples/qa_export").read_bytes()).hexdigest(),
              "engine_revision": run(["git", "rev-parse", "HEAD"]).decode().strip(),
              "working_tree_status": run(["git", "status", "--porcelain"]).decode(),
              "tesseract": run(["tesseract", "--version"]).decode().splitlines()[0],
              "installed_languages": model_data["installed_languages"],
              "ocr_models": model_data, "results": results}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    (output / "index.html").write_text(report_html(results))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path, help="New output directory; never overwrites a run")
    parser.add_argument("--languages", default="eng")
    parser.add_argument("--tessdata-dir", type=Path, help="Directory of local traineddata models")
    args = parser.parse_args()
    benchmark(args.manifest.resolve(), args.output.resolve(), args.languages,
              args.tessdata_dir.resolve() if args.tessdata_dir else None)
