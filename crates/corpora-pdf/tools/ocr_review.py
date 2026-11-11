"""Source-pinned region OCR candidates. Outputs always require source-image review."""

from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import json
import math
import os
import re
import struct
import subprocess
import tempfile
import unicodedata as ud
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import gateway_ocr

MODEL = "mistral-ocr-2512"
SCRIPTS = {
    "hebrew",
    "aramaic",
    "greek",
    "latin",
    "arabic",
    "syriac",
    "ugaritic",
    "phoenician",
    "cuneiform",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encoded(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def distance(left: str, right: str) -> int:
    row = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        next_row = [i]
        for j, b in enumerate(right, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (a != b)))
        row = next_row
    return row[-1]


def clusters(text: str) -> list[tuple[str, list[str]]]:
    result: list[tuple[str, list[str]]] = []
    for char in ud.normalize("NFD", text):
        if ud.category(char).startswith("M"):
            if not result:
                result.append(("", []))
            result[-1][1].append(char)
        else:
            result.append((char, []))
    return result


def compare(reference: str, candidate: str, verified: bool = False) -> dict[str, Any]:
    """Align base characters, then compare marks on each matched base.

    Repeated bases use deterministic minimal edit alignment. A moved mark is a
    deletion and insertion at different bases, never accepted by multiset equality.
    Indexes address NFD base clusters, not raw string character offsets.
    """
    if (len(reference) + 1) * (len(candidate) + 1) > 1_000_000:
        return {
            "status": "comparison_limit_exceeded",
            "confirmed_discrepancy": False,
            "message": "Select a smaller line region for mark alignment.",
        }
    left, right = clusters(reference), clusters(candidate)
    rows = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for i in range(len(left) + 1):
        rows[i][0] = i
    for j in range(len(right) + 1):
        rows[0][j] = j
    for i, (ref_base, _) in enumerate(left, 1):
        for j, (candidate_base, _) in enumerate(right, 1):
            rows[i][j] = min(
                rows[i - 1][j] + 1,
                rows[i][j - 1] + 1,
                rows[i - 1][j - 1] + (ref_base != candidate_base),
            )
    pairs: list[tuple[int | None, int | None]] = []
    i, j = len(left), len(right)
    while i or j:
        if (
            i
            and j
            and rows[i][j] == rows[i - 1][j - 1] + (left[i - 1][0] != right[j - 1][0])
        ):
            pairs.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif i and rows[i][j] == rows[i - 1][j] + 1:
            pairs.append((i - 1, None))
            i -= 1
        else:
            pairs.append((None, j - 1))
            j -= 1
    discrepancies = []
    for a, b in reversed(pairs):
        expected = list(left[a][1]) if a is not None else []
        actual = list(right[b][1]) if b is not None else []
        # Cancel identical marks only when attached to the same aligned base.
        same_base = a is not None and b is not None and left[a][0] == right[b][0]
        if same_base:
            for mark in expected[:]:
                if mark in actual:
                    expected.remove(mark)
                    actual.remove(mark)
        if expected or actual:
            discrepancies.append(
                {
                    "reference_base_index": a,
                    "candidate_base_index": b,
                    "reference_base": left[a][0] if a is not None else None,
                    "candidate_base": right[b][0] if b is not None else None,
                    "missing": [f"U+{ord(c):04X}" for c in expected],
                    "inserted": [f"U+{ord(c):04X}" for c in actual],
                    "kind": "substitution"
                    if expected and actual and same_base
                    else "deletion_insertion",
                }
            )
    ref, cand = ud.normalize("NFD", reference), ud.normalize("NFD", candidate)
    edits = distance(ref, cand)
    return {
        "normalization": "NFD",
        "codepoint_edits": edits,
        "reference_codepoints": len(ref),
        "cer": edits / len(ref) if ref else None,
        "evidence": "image_verified_reference" if verified else "unverified_reference",
        "confirmed_discrepancy": bool(edits) and verified,
        "alignment": "minimal_base_edit_alignment; repeated-base locations can be ambiguous",
        "mark_discrepancies": discrepancies,
    }


def private_json(path: Path, value: Any) -> None:
    """Atomic private output; callers choose an ignored private directory."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded(value) + b"\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def alphabet(model: Path, required: str, scripts: Iterable[str] = ()) -> dict[str, Any]:
    """Read safetensors metadata without importing torch or deserializing pickle."""
    with model.open("rb") as stream:
        prefix = stream.read(8)
        if len(prefix) != 8:
            raise ValueError("invalid safetensors header")
        size = struct.unpack("<Q", prefix)[0]
        if size > 16 * 1024 * 1024:
            raise ValueError("safetensors header too large")
        header = json.loads(stream.read(size))
    metadata = json.loads(header.get("__metadata__", {}).get("kraken_meta", "{}"))
    codecs = [
        entry["codec"]
        for entry in metadata.values()
        if isinstance(entry, dict) and isinstance(entry.get("codec"), dict)
    ]
    if len(codecs) != 1:
        raise ValueError("expected exactly one audited Kraken output codec")
    supported = set(ud.normalize("NFD", "".join(codecs[0])))
    inventories = {
        "hebrew": "אבגדהוזחטיךכלםמןנסעףפץצקרשת",
        "aramaic": "אבגדהוזחטיךכלםמןנסעףפץצקרשת",
        "greek": "αβγδεζηθικλμνξοπρσςτυφχψω",
        "latin": "abcdefghijklmnopqrstuvwxyz",
        "arabic": "ابتثجحخدذرزسشصضطظعغفقكلمنهويء",
        "syriac": "".join(
            chr(c) for c in range(0x710, 0x730) if ud.category(chr(c)).startswith("L")
        ),
    }
    for script in sorted(set(scripts)):
        if script not in inventories:
            raise ValueError("no validated local alphabet policy for script: " + script)
        absent = set(inventories[script]) - supported
        if absent:
            raise ValueError("model lacks required base alphabet for " + script)
    missing = sorted(set(required) - supported)
    if missing:
        raise ValueError(
            "model alphabet lacks: " + ", ".join(f"U+{ord(c):04X}" for c in missing)
        )
    return {
        "required_codepoints": [f"U+{ord(c):04X}" for c in required],
        "scripts": sorted(set(scripts)),
        "passed": True,
    }


def validate_manifest(pdf: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(manifest, dict):
        raise TypeError("manifest must be an object")
    if pdf.stat().st_size > 100 * 1024 * 1024:
        raise ValueError("PDF exceeds 100 MiB limit")
    data = pdf.read_bytes()
    if not data.startswith(b"%PDF-") or digest(data) != manifest.get("source_sha256"):
        raise ValueError("PDF header or source SHA-256 mismatch")
    regions = manifest.get("regions")
    if not isinstance(regions, list) or not 1 <= len(regions) <= 100:
        raise ValueError("manifest requires 1..100 regions")
    ids = set()
    for region in regions:
        if not isinstance(region, dict):
            raise TypeError("regions must be objects")
        identity = region.get("id")
        if not isinstance(identity, str) or not identity or identity in ids:
            raise ValueError("region IDs must be unique nonempty strings")
        ids.add(identity)
        box = region.get("bounds")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
            or not (0 <= box[0] < box[2] <= 1 and 0 <= box[1] < box[3] <= 1)
        ):
            raise ValueError("bounds must be normalized [left, top, right, bottom]")
        if type(region.get("page")) is not int or not 1 <= region["page"] <= 10000:
            raise ValueError("page must be a one-based physical page number")
        if region.get("script") not in SCRIPTS:
            raise ValueError("explicit supported script hint required")
        if (
            not isinstance(region.get("raw_text"), str)
            or len(region["raw_text"]) > 10000
        ):
            raise ValueError("raw_text must be a string of at most 10000 characters")
        if region.get(
            "direction", "L" if region.get("script") in ("greek", "latin") else "R"
        ) not in ("R", "L"):
            raise ValueError("direction must be R or L")
        reference = region.get("reference")
        if reference is not None and (
            not isinstance(reference, dict)
            or not isinstance(reference.get("text"), str)
            or len(reference["text"]) > 10000
            or reference.get("status") not in ("image_verified", "unreviewed")
        ):
            raise ValueError(
                "reference requires text and image_verified/unreviewed status"
            )
        required = region.get("required_marks", "")
        if not isinstance(required, str) or any(
            not ud.category(c).startswith("M") for c in required
        ):
            raise ValueError("required_marks must contain only combining marks")
    return regions


def command(arguments: list[str], timeout: int = 180) -> bytes:
    try:
        return subprocess.run(
            arguments, capture_output=True, check=True, timeout=timeout
        ).stdout
    except (OSError, subprocess.SubprocessError):
        raise ValueError(
            "local tool failed; inspect installation and selected region"
        ) from None


def render(pdf: Path, region: dict[str, Any], work: Path) -> bytes:
    from PIL import Image

    prefix = work / "page"
    command(
        [
            "pdftoppm",
            "-f",
            str(region["page"]),
            "-l",
            str(region["page"]),
            "-singlefile",
            "-scale-to",
            "3200",
            "-png",
            str(pdf),
            str(prefix),
        ]
    )
    with Image.open(prefix.with_suffix(".png")) as page:
        x0, y0, x1, y1 = region["bounds"]
        box = (
            math.floor(x0 * page.width),
            math.floor(y0 * page.height),
            math.ceil(x1 * page.width),
            math.ceil(y1 * page.height),
        )
        crop = work / "crop.png"
        page.crop(box).save(crop)
    return crop.read_bytes()


class HostedOCRError(ValueError):
    """Sanitized direct-provider failure with any validated response accounting."""

    def __init__(self, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(
            "hosted OCR failed or returned invalid output; no retry performed"
        )
        self.metadata = metadata or {}


def hosted_metadata(data: Any) -> dict[str, Any]:
    """Only retain known counters and OCR model identifiers, never response text."""
    metadata: dict[str, Any] = {"requested_model": MODEL, "usage_info": {}}
    if not isinstance(data, dict):
        return metadata
    reported = data.get("model")
    if isinstance(reported, str) and re.fullmatch(
        r"mistral-ocr-(?:[0-9]{4}(?:-[0-9]{2,8})?|latest)(?:-completion)?", reported
    ):
        metadata["reported_model"] = reported
    usage = data.get("usage_info")
    if isinstance(usage, dict):
        metadata["usage_info"] = {
            name: usage[name]
            for name in ("pages_processed", "doc_size_bytes")
            if type(usage.get(name)) is int and usage[name] >= 0
        }
    return metadata


def hosted_response(image: bytes) -> dict[str, Any]:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise ValueError("MISTRAL_API_KEY is required for uncached hosted requests")
    body = {
        "model": MODEL,
        "document": {
            "type": "image_url",
            "image_url": "data:image/png;base64," + base64.b64encode(image).decode(),
        },
        "include_image_base64": False,
    }
    request = urllib.request.Request(
        "https://api.mistral.ai/v1/ocr",
        data=encoded(body),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )

    # Reject redirects so a provider response cannot forward credentials elsewhere.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(
            self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
        ) -> None:
            return None

    metadata: dict[str, Any] = {}
    try:
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=120
        ) as response:
            payload = response.read(2 * 1024 * 1024 + 1)
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError()
        data = json.loads(payload)
        metadata = hosted_metadata(data)
        pages = data["pages"]
        if not isinstance(pages, list) or len(pages) != 1:
            raise ValueError()
        candidate = pages[0]["markdown"]
        if (
            not isinstance(candidate, str)
            or not candidate.strip()
            or len(candidate) > 10000
        ):
            raise ValueError()
        return {"text": candidate, "metadata": metadata}
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        http.client.HTTPException,
    ):
        raise HostedOCRError(metadata) from None


def hosted(image: bytes) -> str:
    """Compatibility wrapper for callers expecting only Markdown."""
    candidate: str = hosted_response(image)["text"]
    return candidate


def local(
    image: bytes, model: Path | None, executable: Path | None, direction: str
) -> str:
    if model is None or executable is None:
        raise ValueError("local model and executable are required")
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        (work / "crop.png").write_bytes(image)
        command(
            [
                str(executable),
                "--device",
                "cpu",
                "--precision",
                "32-true",
                "--threads",
                "2",
                "--raise-on-error",
                "-i",
                str(work / "crop.png"),
                str(work / "out.txt"),
                "ocr",
                "--no-segmentation",
                "--base-dir",
                direction,
                "--num-line-workers",
                "0",
                "-m",
                str(model),
            ]
        )
        return (work / "out.txt").read_text().rstrip("\n")


def run(
    pdf: Path,
    manifest: dict[str, Any],
    output: Path,
    cache: Path,
    provider: str,
    max_calls: int,
    model: Path | None = None,
    kraken: Path | None = None,
    render_region: Callable[[Path, dict[str, Any], Path], bytes] = render,
    hosted_recognize: Callable[[bytes], str | dict[str, Any]] = hosted_response,
    local_recognize: Callable[[bytes, Path | None, Path | None, str], str] = local,
    gateway_recognize: Callable[..., dict[str, Any]] = gateway_ocr.recognize,
    gateway_model: str = gateway_ocr.MODEL,
    gateway_check: Callable[..., dict[str, Any]] = gateway_ocr.check_model,
    gateway_reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if output.resolve() == pdf.resolve() or (
        model is not None and output.resolve() == model.resolve()
    ):
        raise ValueError("output must not overwrite input PDF or model")
    regions = validate_manifest(pdf, manifest)
    if gateway_reasoning_effort is not None and provider != "vercel":
        raise ValueError("Gateway reasoning effort requires the vercel provider")
    if (
        provider not in ("local", "mistral", "vercel")
        or type(max_calls) is not int
        or max_calls < 1
    ):
        raise ValueError("explicit provider and positive max_calls required")
    audit = None
    if provider == "local":
        if (
            model is None
            or kraken is None
            or not model.is_file()
            or not kraken.is_file()
        ):
            raise ValueError(
                "local recognition requires installed model and Kraken paths"
            )
        required = "".join(region.get("required_marks", "") for region in regions)
        audit = alphabet(model, required, [region["script"] for region in regions])
        identity = {
            "model_sha256": digest(model.read_bytes()),
            "kraken_version": command([str(kraken), "--version"]).decode().strip(),
        }
    elif provider == "vercel":
        identity = gateway_ocr.identity(gateway_model, gateway_reasoning_effort)
    else:
        identity = {"model": MODEL}
    # Retain version explicitly rather than relying on empty stdout from Poppler.
    version_result = subprocess.run(
        ["pdftoppm", "-v"], capture_output=True, check=True, timeout=10
    )
    version = (version_result.stderr or version_result.stdout).decode().splitlines()[0]
    report = {
        "schema_version": 1,
        "source_sha256": manifest["source_sha256"],
        "provider": provider,
        "identity": identity,
        "alphabet_audit": audit,
        "calls": 0,
        "regions": [],
    }
    gateway_preflight: dict[str, Any] | gateway_ocr.GatewayError | None = None
    report["preflight_requests"] = 0
    for region in regions:
        with tempfile.TemporaryDirectory() as directory:
            image = render_region(pdf, region, Path(directory))
        key_fields = {
            "version": 1,
            "source_sha256": manifest["source_sha256"],
            "page": region["page"],
            "bounds": region["bounds"],
            "crop_sha256": digest(image),
            "provider": provider,
            "identity": identity,
            "renderer": version,
            "max_edge": 3200,
            "direction": region.get(
                "direction", "L" if region.get("script") in ("greek", "latin") else "R"
            ),
        }
        key = digest(encoded(key_fields))
        cache_path = cache / (key + ".json")
        item = {
            "id": region["id"],
            "page": region["page"],
            "bounds": region["bounds"],
            "coordinate_space": "normalized_page_top_left",
            "script": region["script"],
            "raw_text": region["raw_text"],
            "text_sha256": digest(region["raw_text"].encode()),
            "provenance": key_fields,
            "cache_key": key,
            "missing_marks": None,
            "status": "review_required",
            "message": "Inspect source image; exact missing marks are unknown.",
        }
        recognition_metadata = {}
        if cache_path.exists():
            cached = json.loads(cache_path.read_text())
            if cached.get("cache_key") != key or not isinstance(
                cached.get("text"), str
            ):
                raise ValueError("invalid cached candidate")
            candidate, hit = cached["text"], True
            recognition_metadata = cached.get("recognition_metadata", {})
        elif report["calls"] >= max_calls:
            item.update(status="budget_exhausted", candidate_text=None, cache_hit=False)
            report["regions"].append(item)
            continue
        else:
            try:
                if provider == "vercel":
                    if gateway_preflight is None:
                        report["preflight_requests"] += 1
                        try:
                            gateway_preflight = (
                                gateway_check(gateway_model)
                                if gateway_reasoning_effort is None
                                else gateway_check(
                                    gateway_model, gateway_reasoning_effort
                                )
                            )
                        except gateway_ocr.GatewayError as preflight_error:
                            gateway_preflight = preflight_error
                    if isinstance(gateway_preflight, gateway_ocr.GatewayError):
                        raise gateway_preflight
                    report["model_eligibility"] = gateway_preflight
                report["calls"] += 1
                if provider == "vercel":
                    response = (
                        gateway_recognize(image, gateway_model)
                        if gateway_reasoning_effort is None
                        else gateway_recognize(
                            image, gateway_model, gateway_reasoning_effort
                        )
                    )
                    candidate = response["text"]
                    recognition_metadata = response["metadata"]
                elif provider == "mistral":
                    hosted_result = hosted_recognize(image)
                    if isinstance(hosted_result, dict):
                        candidate = hosted_result.get("text")
                        recognition_metadata = hosted_result.get("metadata", {})
                        if not isinstance(recognition_metadata, dict):
                            raise HostedOCRError()
                    else:
                        candidate = hosted_result
                else:
                    candidate = local_recognize(
                        image,
                        model,
                        kraken,
                        region.get(
                            "direction",
                            "L" if region.get("script") in ("greek", "latin") else "R",
                        ),
                    )
                if (
                    not isinstance(candidate, str)
                    or not candidate.strip()
                    or len(candidate) > 10000
                ):
                    raise ValueError("invalid candidate")
                private_json(
                    cache_path,
                    {
                        "cache_key": key,
                        "text": candidate,
                        "recognition_metadata": recognition_metadata,
                    },
                )
                hit = False
            except (OSError, ValueError, subprocess.SubprocessError) as error:
                item.update(
                    status="recognition_failed",
                    candidate_text=None,
                    cache_hit=False,
                    message="Recognition failed; no retry performed. Raw text retained.",
                )
                if isinstance(error, gateway_ocr.GatewayError):
                    item["error_code"] = error.code
                    item["http_status"] = error.http_status
                    if error.metadata:
                        item["recognition_metadata"] = error.metadata
                elif isinstance(error, HostedOCRError):
                    item["error_code"] = "hosted_ocr_failed"
                    if error.metadata:
                        item["recognition_metadata"] = error.metadata
                report["regions"].append(item)
                continue
        item.update(
            candidate_text=candidate,
            recognition_metadata=recognition_metadata,
            cache_hit=hit,
            output_format="markdown" if provider == "mistral" else "plain_text",
        )
        if region.get("reference"):
            ref = region["reference"]
            item["comparison"] = compare(
                ref["text"], candidate, ref["status"] == "image_verified"
            )
        report["regions"].append(item)
    private_json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument(
        "--provider", choices=("local", "mistral", "vercel"), required=True
    )
    parser.add_argument("--max-calls", type=int, required=True)
    parser.add_argument("--model", type=Path)
    parser.add_argument("--kraken", type=Path)
    parser.add_argument(
        "--gateway-model",
        default=gateway_ocr.MODEL,
        help="explicit Gateway model; no model fallback",
    )
    parser.add_argument(
        "--gateway-reasoning-effort",
        choices=("low", "high"),
        help="explicit reasoning effort; must be advertised by the selected Gateway model",
    )
    args = parser.parse_args()
    if args.output.resolve() == args.manifest.resolve():
        parser.exit(2, "output must not overwrite the input manifest\n")
    try:
        report = run(
            args.pdf,
            json.loads(args.manifest.read_text()),
            args.output,
            args.cache,
            args.provider,
            args.max_calls,
            args.model,
            args.kraken,
            gateway_model=args.gateway_model,
            gateway_reasoning_effort=args.gateway_reasoning_effort,
        )
    except (ValueError, TypeError, OSError, subprocess.SubprocessError):
        parser.exit(
            2,
            "OCR review failed validation or local processing; check paths, manifest and tools.\n",
        )
    print(
        f"{len(report['regions'])} regions; {report['calls']} recognition calls; output: {args.output}"
    )
    return 1 if any(r["status"] != "review_required" for r in report["regions"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
