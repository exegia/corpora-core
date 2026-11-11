"""Score held-out line candidates against human-reviewed references.

Implements the metrics and thresholds pre-registered in PHASE2.md ("Held-out
line benchmark"). Inputs are an `ocr_review.py` report per model and the
reviewed reference ledger; nothing here calls a model.
"""

import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path

APOSTROPHES = {"'", "’", "ʼ", "᾽", "᾿"}
DIVINE_NAME = "יהוה"
THRESHOLDS = {"completion_min": 0.98, "base_error_max": 0.01, "mark_error_max": 0.02,
              "divine_violations_max": 0}


def clusters(text):
    """NFD text -> [(base, Counter(marks))]; apostrophe forms folded, whitespace collapsed."""
    text = " ".join(unicodedata.normalize("NFD", text).split())
    out = []
    for ch in text:
        if ch in APOSTROPHES:
            ch = "’"
        if unicodedata.combining(ch):
            if not out:
                out.append(["", Counter()])
            out[-1][1][ch] += 1
        else:
            out.append([ch, Counter()])
    return [(b, m) for b, m in out]


def align(ref, cand):
    """Minimal base-edit alignment: list of (ref_index|None, cand_index|None)."""
    n, m = len(ref), len(cand)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                          d[i - 1][j - 1] + (ref[i - 1][0] != cand[j - 1][0]))
    pairs, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (ref[i - 1][0] != cand[j - 1][0]):
            pairs.append((i - 1, j - 1)); i -= 1; j -= 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            pairs.append((i - 1, None)); i -= 1
        else:
            pairs.append((None, j - 1)); j -= 1
    return d[n][m], pairs[::-1]


def score_line(reference, candidate):
    ref, cand = clusters(reference), clusters(candidate)
    edits, pairs = align(ref, cand)
    missing = inserted = 0
    for i, j in pairs:
        rm = ref[i][1] if i is not None else Counter()
        cm = cand[j][1] if j is not None else Counter()
        missing += sum((rm - cm).values())
        inserted += sum((cm - rm).values())
    to_cand = {i: j for i, j in pairs if i is not None}
    bases = "".join(b for b, _ in ref)
    violations = 0
    start = bases.find(DIVINE_NAME)
    while start != -1:
        span = range(start, start + len(DIVINE_NAME))
        if not any(ref[k][1] for k in span):  # only an unpointed name in the reference counts
            if any(to_cand.get(k) is not None and cand[to_cand[k]][1] for k in span):
                violations += 1
        start = bases.find(DIVINE_NAME, start + 1)
    return {"base_edits": edits, "reference_bases": len(ref),
            "missing_marks": missing, "inserted_marks": inserted,
            "reference_marks": sum(sum(m.values()) for _, m in ref),
            "divine_violations": violations}


def pool(lines):
    """lines: [{"reference": str, "candidate": str|None}] for one script and model."""
    sent = len(lines)
    complete = [x for x in lines if x.get("candidate")]
    scores = [score_line(x["reference"], x["candidate"]) for x in complete]
    total = lambda key: sum(s[key] for s in scores)
    ref_bases, ref_marks = total("reference_bases"), total("reference_marks")
    metrics = {
        "lines_sent": sent, "lines_complete": len(complete),
        "completion": len(complete) / sent if sent else 0.0,
        "base_error": total("base_edits") / ref_bases if ref_bases else None,
        "mark_error": (total("missing_marks") + total("inserted_marks")) / ref_marks if ref_marks else None,
        "missing_marks": total("missing_marks"), "inserted_marks": total("inserted_marks"),
        "reference_marks": ref_marks, "reference_bases": ref_bases,
        "divine_violations": total("divine_violations"),
    }
    metrics["passes"] = passes(metrics)
    return metrics


def passes(m):
    return (m["completion"] >= THRESHOLDS["completion_min"]
            and m["base_error"] is not None and m["base_error"] <= THRESHOLDS["base_error_max"]
            and (m["mark_error"] is None or m["mark_error"] <= THRESHOLDS["mark_error_max"])
            and m["divine_violations"] <= THRESHOLDS["divine_violations_max"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ledger", type=Path, help="reviewed reference-ledger.json")
    parser.add_argument("reports", type=Path, nargs="+", help="ocr_review.py report JSON files")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    ledger = {x["id"]: x for x in json.loads(args.ledger.read_text())["lines"]
              if x.get("status") in ("approved", "corrected")}
    groups = {}
    for path in args.reports:
        report = json.loads(path.read_text())
        model = report["identity"]["model"]
        for region in report["regions"]:
            line = ledger.get(region["id"])
            if line is None:
                continue
            ok = region.get("status") == "review_required" and region.get("candidate_text")
            groups.setdefault((model, line["script"]), []).append(
                {"reference": line["text"], "candidate": region["candidate_text"] if ok else None})
    result = {f"{model} | {script}": pool(lines) for (model, script), lines in sorted(groups.items())}
    text = json.dumps({"thresholds": THRESHOLDS, "results": result}, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
