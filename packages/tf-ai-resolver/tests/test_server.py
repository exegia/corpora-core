"""Local HTTP selection bridge, including origin and source-span checks."""

import json
import threading
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from tf.fabric import Fabric

from tf_ai_resolver.server import create_server


class FakeExpert:
    model = "fixture"

    def propose(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert payload["selected_text"] == "β"
        return {"action": "replace", "replacement": "B", "reason": "Corrected"}


def corpus(path: Path) -> Path:
    path.mkdir()
    assert Fabric(locations=str(path), silent="deep").save(
        nodeFeatures={
            "otype": {1: "character", 2: "character", 3: "character", 4: "document"},
            "reading": {1: "A", 2: "β", 3: "C"},
            "document": {4: "mini"},
        },
        edgeFeatures={"oslots": {4: {1, 2, 3}}},
        metaData={
            "otype": {"valueType": "str"},
            "oslots": {"valueType": "str"},
            "reading": {"valueType": "str"},
            "document": {"valueType": "str"},
            "otext": {
                "fmt:text-orig-full": "{reading}",
                "sectionTypes": "document",
                "sectionFeatures": "document",
            },
        },
        silent="deep",
    )
    return path


def test_local_page_inspects_and_resolves_a_selection(tmp_path: Path) -> None:
    source = corpus(tmp_path / "tf")
    site = tmp_path / "site"
    (site / "tf-rendered").mkdir(parents=True)
    (site / "index.html").write_text(
        '<iframe id="tf-rendered" class="source-view" sandbox=""></iframe></html>'
    )
    (site / "tf-rendered/0001.html").write_text('<main data-tf-node="4">AβC</main>')
    output_root = tmp_path / "resolutions"
    server = create_server(site, source, output_root, FakeExpert())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def post(path: str, body: dict[str, Any], origin: str = base) -> tuple[int, dict[str, Any]]:
        request = Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
                "X-TF-Resolver": "1",
            },
        )
        try:
            with urlopen(request) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    try:
        with urlopen(base + "/") as response:
            page = response.read().decode()
        assert 'sandbox="allow-same-origin"' in page
        assert '<script src="/tf-resolver.js"></script>' in page
        with urlopen(base + "/tf-resolver.js") as response:
            assert b"data-tf-node" in response.read()
        status, _ = post(
            "/api/inspect", {"node": 4, "start": 1, "end": 2, "expected_text": "β"}, "http://evil"
        )
        assert status == 403
        status, _ = post("/api/inspect", {"node": 4, "start": 1, "end": 2, "expected_text": "B"})
        assert status == 422
        status, inspected = post(
            "/api/inspect", {"node": 4, "start": 1, "end": 2, "expected_text": "β"}
        )
        assert status == 200
        status, resolved = post(
            "/api/resolve",
            {
                "selection": inspected["selection"],
                "mode": "fix",
                "prompt": "Correct the selected character",
            },
        )
        assert status == 200
        assert resolved["report"]["resolution"]["replacement"] == "B"
        assert (Path(resolved["output"]) / "tf/ai_resolutions.tf").is_file()
        assert not (source / "ai_resolutions.tf").exists()
        status, rejected = post(
            "/api/apply",
            {
                "proposal_id": resolved["proposal_id"],
                "resolution_id": resolved["report"]["resolution"]["id"],
                "expected_replacement": "Wrong",
            },
        )
        assert status == 422 and "does not match" in rejected["error"]
        status, applied = post(
            "/api/apply",
            {
                "proposal_id": resolved["proposal_id"],
                "resolution_id": resolved["report"]["resolution"]["id"],
                "expected_replacement": "B",
            },
        )
        assert status == 200
        assert applied["report"]["resolution"]["status"] == "applied"
        assert (Path(applied["output"]) / "tf/resolved_reading.tf").is_file()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
