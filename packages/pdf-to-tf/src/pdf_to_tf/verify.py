"""Check the loaded TF graph against the extraction, line by line and word by word."""

from pathlib import Path
from typing import Any

from tf.fabric import Fabric

from .issues import Issue, excerpt
from .tei import XML_ID, Mapped

ZONE = ("facs_ulx", "facs_uly", "facs_lrx", "facs_lry")


def verify(tf_dir: Path, graph: dict[str, Any], mapped: list[Mapped]) -> dict[str, Any]:
    names = graph["attribute_features"]
    id_feature = names.get(XML_ID)
    cert_feature = names.get("cert")
    features = ["otype", "text", "page", "tei_tag", "facs_surface", *ZONE]
    features += [n for n in (id_feature, cert_feature) if n]
    present = [f for f in features if (tf_dir / f"{f}.tf").exists()]
    api = Fabric(locations=str(tf_dir), silent="deep").load(" ".join(present), silent="deep")
    if not api:
        raise RuntimeError("Text-Fabric could not load the converted feature set")
    F, L, T = api.F, api.L, api.T
    node_of: dict[str, int] = {}
    if id_feature:
        for node in F.otype.s("element"):
            ident = getattr(F, id_feature).v(node)
            if ident:
                node_of[ident] = node
    mismatches: list[Issue] = []
    checked = {"lines": 0, "words": 0, "pages": 0, "zero_width": 0, "omitted": 0}

    def fail(item: Mapped, detail: str, word: int | None = None) -> None:
        mismatches.append(
            Issue(
                "verification_mismatch",
                detail,
                item.page,
                item.index,
                word,
                text=excerpt(item.text),
                xml_id=item.xml_id,
                tf_node=node_of.get(item.xml_id),
            )
        )

    def zone_matches(node: int, zone: tuple[int, int, int, int] | None) -> bool:
        return zone is None or tuple(getattr(F, f).v(node) for f in ZONE) == zone

    for item in mapped:
        if item.status != "projected":
            checked["zero_width" if item.status == "zero-width" else "omitted"] += 1
            if item.xml_id in node_of:
                fail(item, f"{item.status} element unexpectedly has TF slots")
            continue
        node = node_of.get(item.xml_id)
        if node is None:
            fail(item, "no TF element node for this line")
            continue
        checked["lines"] += 1
        if T.text(node) != item.text:
            fail(item, f"TF text {excerpt(T.text(node), 60)!r} differs from extraction")
        if F.tei_tag.v(node) != item.tei_tag:
            fail(item, f"TF tei_tag {F.tei_tag.v(node)!r} is not {item.tei_tag!r}")
        if not zone_matches(node, item.zone) or F.facs_surface.v(node) != str(item.page):
            fail(item, "TF zone features differ from the extraction bounds")
        pages = L.u(node, otype="page")
        if [F.page.v(p) for p in pages] != [str(item.page)]:
            fail(item, f"line is not inside TF page {item.page}")
        for number, word in enumerate(item.words):
            checked["words"] += 1
            wnode = node_of.get(word["xml_id"])
            if wnode is None or T.text(wnode) != word["text"]:
                fail(item, f"word {word['xml_id']} text differs in TF", number)
            elif not zone_matches(wnode, word["zone"]):
                fail(item, f"word {word['xml_id']} zone differs in TF", number)
            elif cert_feature and getattr(F, cert_feature).v(wnode) != word["cert"]:
                fail(item, f"word {word['xml_id']} confidence differs in TF", number)
    expected_pages = {str(m.page) for m in mapped if m.status == "projected"}
    tf_pages = {F.page.v(n): n for n in F.otype.s("page")}
    checked["pages"] = len(tf_pages)
    for label in sorted(expected_pages - set(tf_pages), key=int):
        mismatches.append(
            Issue("verification_mismatch", f"no TF page node for page {label}", int(label))
        )
    for label, node in tf_pages.items():
        if F.facs_surface.v(node) != label:
            mismatches.append(
                Issue("verification_mismatch", "page surface differs", int(label), tf_node=node)
            )
    outside = graph.get("pages", {}).get("characters_outside_pages", 0)
    if outside:
        mismatches.append(
            Issue("verification_mismatch", f"{outside} TF characters are outside every page")
        )
    return {"checked": checked, "mismatches": mismatches, "node_of": node_of}
