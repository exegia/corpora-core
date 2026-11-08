"""Pinned Baudelaire regression and independent TEI/TF HTML comparison views."""

import argparse
import hashlib
import html
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from cfabric.core import Fabric as ContextFabric
from lxml import etree
from tf.fabric import Fabric

from .acquire import acquire
from .convert import convert, write_json
from .model import ConversionError
from .parse import TEI, secure_tree

REVISION = "71fb49a3738a4533913327beffb39fd90633b0f1"
SOURCE_URL = (
    f"https://github.com/CliffordAnderson/corpus-baudelaire/blob/{REVISION}/"
    "fleurs-du-mal/FDM-000-000-000-087.xml"
)
SOURCE_SHA256 = "d3ae54bc4775bc5efbc107f5ee63fbddf0b7a3b03a86b060a21f3874de8ce4b6"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ConversionError(message)


def source_view(data: bytes) -> dict[str, Any]:
    """Independent XPath reading oracle: deliberately does not call converter projection."""
    root = secure_tree(data).getroot()
    ns = {"t": TEI}
    body = root.find("t:text/t:body", ns)
    require(body is not None, "Fixture has no TEI body")
    assert body is not None
    poem = body.find("t:div", ns)
    require(poem is not None, "Fixture has no poem division")
    assert poem is not None

    def text(node: etree._Element) -> str:
        return "".join(x.decode() if isinstance(x, bytes) else x for x in node.itertext())

    head = poem.find("t:head", ns)
    require(head is not None, "Fixture has no poem heading")
    assert head is not None
    stanzas = []
    for group in poem.findall("t:lg", ns):
        stanzas.append(
            {
                "number": group.get("n"),
                "subtype": group.get("subtype"),
                "text": text(group),
                "lines": [
                    {"number": line.get("n"), "text": text(line)}
                    for line in group.findall("t:l", ns)
                ],
            }
        )
    return {
        "title": text(head).strip(),
        "head_text": text(head),
        "body": text(body),
        "stanzas": stanzas,
    }


def tf_view(api: Any) -> dict[str, Any]:
    """Render only data read from the TF graph;
    no document text/outline sidecar."""
    elements = list(api.F.otype.s("element"))

    def nodes(tag: str) -> list[int]:
        return sorted(
            (n for n in elements if api.F.tei_tag.v(n) == tag), key=lambda n: (api.F.start.v(n), n)
        )

    def attributes(n: int) -> dict[str, str]:
        result: dict[str, str] = json.loads(api.F.attributes.v(n))
        return result

    heads, bodies = nodes("head"), nodes("body")
    require(len(heads) == len(bodies) == 1, "Expected one body and one heading")
    lines = nodes("l")
    stanzas = []
    for group in nodes("lg"):
        attrs = attributes(group)
        children = [n for n in lines if tuple(api.E.parent.f(n)) == (group,)]
        stanzas.append(
            {
                "number": attrs.get("n"),
                "subtype": attrs.get("subtype"),
                "text": api.T.text(group),
                "lines": [
                    {"number": attributes(n).get("n"), "text": api.T.text(n)} for n in children
                ],
            }
        )
    return {
        "title": api.T.text(heads[0]).strip(),
        "head_text": api.T.text(heads[0]),
        "body": api.T.text(bodies[0]),
        "stanzas": stanzas,
    }


def verify_projection(api: Any, expected: dict[str, Any]) -> dict[str, Any]:
    actual = tf_view(api)
    require(actual == expected, "TF content/heading/stanza/line graph differs from independent TEI")
    chars = [api.F.text.v(n) for n in range(1, api.F.otype.maxSlot + 1)]
    require(chars == list(expected["body"]), "Slot values differ from source Unicode scalars")
    require(all(len(char) == 1 for char in chars), "Empty or multi-character slot found")
    require(
        all(api.T.text(n) == char for n, char in enumerate(chars, 1)),
        "A slot's rendered text differs from its exact source character",
    )
    for n in api.F.otype.s("element"):
        start, end = api.F.start.v(n), api.F.end.v(n)
        require(api.T.text(n) == expected["body"][start:end], "Element span/text mismatch")
    for n in api.F.otype.s("block"):
        require(api.T.nodeFromSection(api.T.sectionFromNode(n)) == n, "Section round trip failed")
    return {
        "characters": len(chars),
        "whitespace_characters": sum(c.isspace() for c in chars),
        "empty_slots": 0,
        "stanzas": len(actual["stanzas"]),
        "lines": sum(len(s["lines"]) for s in actual["stanzas"]),
    }


STYLE = """
:root { color-scheme: dark;
font-family: system-ui, sans-serif;
color:#dedfe3;
background:#15171b;
}
* { box-sizing:border-box;
} body { margin:0;
} header { padding:22px 30px;
border-bottom:1px solid #353a43;
background:#1d2026;
} nav { display:flex;
gap:18px;
font-size:13px;
margin-top:12px;
}
a { color:#91bde3;
} .eyebrow { font-size:12px;
text-transform:uppercase;
letter-spacing:.13em;
color:#a4acb8;
}
h1 { font:normal 30px Georgia,serif;
margin:12px 0 6px;
} .status { color:#8bc7a8;
font-size:13px;
}
main { max-width:830px;
margin:28px auto;
padding:0 30px 40px;
}
article { background:#1d2026;
padding:28px 28px 20px;
border:1px solid #353a43;
border-radius:5px;
}
.stanza { margin:0 0 24px;
} .line { display:flex;
gap:18px;
margin:8px 0;
}
.number { width:22px;
flex-shrink:0;
font:12px system-ui;
color:#8b9295;
padding-top:6px;
text-align:right;
}
.verse { font:19px/1.6 Georgia,serif;
white-space:pre-wrap;
} details { margin-top:20px;
}
summary { cursor:pointer;
color:#b5becb;
font-size:13px;
} pre { overflow:auto;
white-space:pre-wrap;
font:12px/1.6 ui-monospace,monospace;
padding:16px;
background:#22262e;
}
.badge { display:inline-block;
padding:4px 9px;
border-radius:4px;
background:#293747;
}
.tf .badge { background:#273d33;
} .comparison { display:grid;
grid-template-columns:1fr 1fr;
height:calc(100vh - 135px);
}
iframe { width:100%;
height:100%;
border:0;
border-right:1px solid #ccc;
}
@media(max-width:850px) { .comparison { display:block;
height:auto;
} iframe { height:900px;
}
main { padding:0 12px 24px;
} article { padding:18px 12px;
} .verse { font-size:17px;
} }
"""


def page(view: dict[str, Any], kind: str, receipt: dict[str, Any]) -> str:
    stanzas = []
    for stanza in view["stanzas"]:
        lines = "".join(
            f'<div class="line"><span class="number">{html.escape(line["number"] or "")}</span>'
            f'<span class="verse">{html.escape(line["text"])}</span></div>'
            for line in stanza["lines"]
        )
        stanzas.append(
            f'<section class="stanza" aria-label="Stanza {stanza["number"]}">{lines}</section>'
        )
    label = "TEI source" if kind == "tei" else "Text-Fabric output"
    method = (
        "Read directly from the original TEI XML"
        if kind == "tei"
        else "Read from TF features and parent edges through the real Text-Fabric loader"
    )
    return f'''<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{label} · Le Couvercle</title>
<style>{STYLE}</style>
<body class="{kind}">
<header>
<div class="eyebrow">
<span class="badge">{label}</span>
 · Charles Baudelaire</div>
<h1>{html.escape(view["title"])}</h1>
<div class="status">Text match verified · 14 lines · 4 stanzas · Exact text matches</div>
<nav>
<a href="index.html"
 target="_top">Side-by-side comparison</a>
<a href="{"tf" if kind == "tei" else "tei"}.html"
 target="_top">Other view</a>
<a href="qa-report.json"
 target="_blank">QA report</a>
<a href="source.xml"
 target="_blank">Original XML</a>
</nav>
</header>
<main>
<article>{"".join(stanzas)}</article>
<details>
<summary>Reading and validation details</summary>
<p>{method}. Display respects stanza and verse structure;
XML indentation is visible below.</p>
<p>The external static validator flags whitespace slots (TF064). Exhaustive checks confirm that all
{receipt["characters"]} characters, including
{receipt["whitespace_characters"]} whitespace characters,
match the source. There are no empty slots. The raw report is retained.</p>
<p>
<a href="validation.md"
 target="_blank">Raw static validation report</a>
</p>
</details>
<details>
<summary>Exact body text · includes XML whitespace</summary>
<pre>{html.escape(view["body"])}</pre>
</details>
</main>
</body>
</html>'''


def run(output: Path, validator: Path, source_file: Path | None = None) -> dict[str, Any]:
    require(validator.is_file(), "Supply the existing text-fabric-validator tf_validate.py script")
    sources = acquire([str(source_file)] if source_file else [SOURCE_URL])
    require(len(sources) == 1, "Expected exactly one pinned source file")
    source = sources[0]
    require(
        hashlib.sha256(source.data).hexdigest() == SOURCE_SHA256, "Pinned fixture SHA-256 changed"
    )
    expected = source_view(source.data)
    require(expected["title"] == "LE COUVERCLE", "Unexpected poem title")
    require(
        [len(s["lines"]) for s in expected["stanzas"]] == [4, 4, 3, 3], "Unexpected stanza shape"
    )
    require(
        [line["number"] for s in expected["stanzas"] for line in s["lines"]]
        == [str(i) for i in range(1, 15)],
        "Unexpected verse numbering",
    )
    manifest = convert([], output, sources=sources)
    document = json.loads(next((output / "documents").glob("*.json")).read_text())
    require(document["metadata"]["authors"] == ["Charles Baudelaire"], "Author extraction changed")
    require(
        document["metadata"]["publishers"] == ["Jean and Alexander Heard Library"],
        "Publication metadata extraction changed",
    )
    require(
        "Jean and Alexander Heard Library" not in expected["body"], "Publisher leaked into text"
    )
    receipts = {}
    features = "text tei_tag attributes start end parent document region block"
    with tempfile.TemporaryDirectory(prefix="baudelaire-loaders-") as temp:
        for name, factory in (("text-fabric", Fabric), ("context-fabric", ContextFabric)):
            root = Path(temp) / name
            root.mkdir()
            for file in (output / "tf").glob("*.tf"):
                shutil.copyfile(file, root / file.name)
            for phase in ("cold", "warm"):
                api = factory(locations=str(root), silent="deep").load(features, silent="deep")
                require(api is not False, f"{name} {phase} failed to load")
                receipts[f"{name}-{phase}"] = verify_projection(api, expected)
                if name == "text-fabric" and phase == "warm":
                    rendered_tf = tf_view(api)
    web = output / "browser"
    web.mkdir()
    process = subprocess.run(
        [
            sys.executable,
            str(validator),
            str(output / "tf"),
            "--report",
            str(web / "validation.md"),
            "--json",
            str(web / "validation.json"),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    require(process.returncode in {0, 1}, f"Static validator could not run: {process.stderr}")
    raw = json.loads((web / "validation.json").read_text())
    errors = [issue for issue in raw["issues"] if issue["severity"] == "error"]
    # This exception is valid only after exhaustive exact scalar/renderer comparison above.
    require(
        all(issue["code"] == "TF064" for issue in errors), "Unresolved static validation errors"
    )
    report = {
        "status": "passed-with-proven-whitespace-exception",
        "source_url": SOURCE_URL,
        "source_revision": REVISION,
        "source_sha256": SOURCE_SHA256,
        "loaders": receipts,
        "static_validator_raw_exit": process.returncode,
        "static_validator_raw_counts": raw["counts"],
        "adjudication": {
            "TF064": "All slots are one exact source scalar; whitespace is not missing text.",
            "TF065": "Character slots must not have invented separators.",
        },
        "schema_validation": "not performed; XML schema hints retained, not fetched",
        "document": manifest["documents"][0],
        "checks": [
            "exact body",
            "heading",
            "14 verses",
            "4 stanzas and parent edges",
            "all element spans",
            "all slot renderings",
            "section round trips",
            "header metadata kept outside corpus",
            "TF and CF cold/warm loads",
        ],
    }
    write_json(web / "qa-report.json", report)
    (web / "source.xml").write_bytes(source.data)
    proof = receipts["text-fabric-warm"]
    (web / "tei.html").write_text(page(expected, "tei", proof), encoding="utf-8")
    (web / "tf.html").write_text(page(rendered_tf, "tf", proof), encoding="utf-8")
    (web / "index.html").write_text(
        f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Le Couvercle · TEI ↔ TF comparison</title>
<style>{STYLE}</style>
<header>
<div class="eyebrow">Conversion QA · Charles Baudelaire</div>
<h1>Le Couvercle</h1>
<div class="status">Exact source-to-TF match · 14 verses · 4 stanzas · Both loaders verified</div>
<nav>
<a href="tei.html"
 target="_blank">Open TEI browser</a>
<a href="tf.html"
 target="_blank">Open TF browser</a>
<a href="qa-report.json"
 target="_blank">Validation evidence</a>
</nav>
</header>
<div class="comparison">
<iframe title="TEI source browser" src="tei.html">
</iframe>
<iframe title="Text-Fabric browser" src="tf.html">
</iframe>
</div>
</html>""",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validator", type=Path, required=True)
    parser.add_argument(
        "--source-file", type=Path, help="Optional cached copy; pinned hash still enforced"
    )
    args = parser.parse_args(argv)
    try:
        result = run(args.output, args.validator, args.source_file)
        print(
            json.dumps(
                {"status": result["status"], "browser": str(args.output / "browser/index.html")}
            )
        )
        return 0
    except (ConversionError, OSError, KeyError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
