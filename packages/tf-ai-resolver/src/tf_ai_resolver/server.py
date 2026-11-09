"""Loopback HTTP bridge from semantic EPUB QA selections to audited TF proposals."""

import json
import re
import threading
import uuid
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

from .api import Expert, ResolveError, Selection, apply_resolution, inspect_selection, resolve

MAX_REQUEST_BYTES = 16 * 1024


def create_server(
    site: Path,
    tf_dir: Path,
    output_root: Path,
    expert: Expert,
    port: int = 0,
) -> ThreadingHTTPServer:
    """Serve a generated QA site and accept same-origin, exact-span requests."""
    site = site.resolve()
    tf_dir = tf_dir.resolve()
    output_root = output_root.resolve()
    index = site / "index.html"
    if not index.is_file() or not (site / "tf-rendered").is_dir():
        raise ResolveError("Expected a generated EPUB QA site")
    rendered_pages = sorted((site / "tf-rendered").glob("*.html"))
    if not rendered_pages or any(
        b"data-tf-node" not in path.read_bytes() for path in rendered_pages
    ):
        raise ResolveError("Regenerate the QA site with TF node selection metadata")
    if not (tf_dir / "otype.tf").is_file():
        raise ResolveError("Expected an exported Text-Fabric directory")
    if site == output_root or site in output_root.parents:
        raise ResolveError("Resolution output must be outside the served QA site")
    page = index.read_text(encoding="utf-8")
    page, iframe_count = re.subn(
        r'(<iframe id="tf-rendered"[^>]*?)sandbox=""',
        r'\1sandbox="allow-same-origin"',
        page,
        count=1,
    )
    if iframe_count != 1 or "</html>" not in page:
        raise ResolveError("QA site lacks the expected semantic TF iframe")
    page = page.replace("</html>", '<script src="/tf-resolver.js"></script></html>', 1)
    output_root.mkdir(parents=True, exist_ok=True)
    busy = threading.Lock()
    issued: dict[str, Path] = {}

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(site), **kwargs)

        def translate_path(self, path: str) -> str:
            candidate = Path(super().translate_path(path)).resolve()
            if not candidate.is_relative_to(site):
                return str(site / "__missing__")
            return str(candidate)

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            data = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path in {"/", "/index.html"}:
                data = page.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path == "/tf-resolver.js":
                data = files("tf_ai_resolver").joinpath("resolver_ui.js").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            super().do_GET()

        def do_POST(self) -> None:
            path = urlsplit(self.path).path
            if path not in {"/api/inspect", "/api/resolve", "/api/apply"}:
                self._json(404, {"error": "Unknown resolver endpoint"})
                return
            server_port = cast(ThreadingHTTPServer, self.server).server_port
            expected_origin = f"http://127.0.0.1:{server_port}"
            if (
                self.headers.get("Origin") != expected_origin
                or self.headers.get("Host") != f"127.0.0.1:{server_port}"
                or self.headers.get("X-TF-Resolver") != "1"
                or self.headers.get_content_type() != "application/json"
            ):
                self._json(403, {"error": "Resolver requests must come from this local QA page"})
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_REQUEST_BYTES:
                    raise ResolveError("Request body is empty or too large")
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ResolveError("Request body must be a JSON object")
                if path == "/api/inspect":
                    if set(body) != {"node", "start", "end", "expected_text"}:
                        raise ResolveError("Selection needs node, offsets, and expected text")
                    selection = inspect_selection(
                        tf_dir, body["node"], body["start"], body["end"], "reading"
                    )
                    if selection.expected_text != body["expected_text"]:
                        raise ResolveError("Browser selection differs from the TF reading")
                    self._json(200, {"selection": asdict(selection)})
                    return
                if path == "/api/apply":
                    if set(body) != {"proposal_id", "resolution_id", "expected_replacement"}:
                        raise ResolveError("Apply needs the exact proposal and replacement")
                    if not busy.acquire(blocking=False):
                        self._json(409, {"error": "The TF expert is already resolving a selection"})
                        return
                    try:
                        proposal_dir = issued.get(body["proposal_id"])
                        if proposal_dir is None:
                            raise ResolveError("Proposal was not issued by this local session")
                        destination = output_root / f"applied-{uuid.uuid4().hex}"
                        report = apply_resolution(
                            proposal_dir,
                            destination,
                            body["resolution_id"],
                            body["expected_replacement"],
                        )
                        del issued[body["proposal_id"]]
                    finally:
                        busy.release()
                    self._json(200, {"output": str(destination), "report": report})
                    return
                if set(body) != {"selection", "mode", "prompt"}:
                    raise ResolveError("Resolution needs selection, mode, and prompt")
                if not isinstance(body["selection"], dict):
                    raise ResolveError("Selection must be an object")
                try:
                    selection = Selection(**body["selection"])
                except TypeError as error:
                    raise ResolveError("Selection fields are invalid") from error
                if not busy.acquire(blocking=False):
                    self._json(409, {"error": "The TF expert is already resolving a selection"})
                    return
                try:
                    destination = output_root / f"resolution-{uuid.uuid4().hex}"
                    report = resolve(
                        tf_dir, destination, selection, body["mode"], body["prompt"], expert
                    )
                    proposal_id = uuid.uuid4().hex
                    issued[proposal_id] = destination
                finally:
                    busy.release()
                self._json(
                    200, {"output": str(destination), "proposal_id": proposal_id, "report": report}
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                self._json(422, {"error": str(error)})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
