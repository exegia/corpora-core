"""Bounded local/HTTPS acquisition, pinning repository inputs to commits."""

import ipaddress
import json
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, unquote, urljoin, urlsplit

import httpx

from .model import ConversionError, Source

SUFFIXES = {".xml", ".tei", ".odd", ".rng", ".xsd", ".json", ".yaml", ".yml", ".md", ".txt"}


@dataclass(frozen=True)
class Limits:
    max_files: int = 1000
    max_file_bytes: int = 64 * 1024 * 1024
    max_total_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        if min(self.max_files, self.max_file_bytes, self.max_total_bytes) < 1:
            raise ConversionError("Acquisition limits must be positive")


def public_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ConversionError("Only credential-free public HTTPS URLs are accepted")
    if parsed.port not in {None, 443}:
        raise ConversionError("Only HTTPS port 443 is accepted")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise ConversionError(f"Cannot resolve host {parsed.hostname}") from exc
    if not addresses or any(not ipaddress.ip_address(x[4][0]).is_global for x in addresses):
        raise ConversionError("Private/local network URLs are not accepted")


def fetch(url: str, limit: int) -> bytes:
    """Fetch bounded identity-encoded bytes with public-address preflight checks."""
    with httpx.Client(timeout=30, trust_env=False, follow_redirects=False) as client:
        for _ in range(6):
            public_url(url)
            with client.stream(
                "GET",
                url,
                headers={"User-Agent": "corpora-tei-to-tf", "Accept-Encoding": "identity"},
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ConversionError("Redirect has no Location")
                    url = urljoin(url, location)
                    continue
                response.raise_for_status()
                if response.headers.get("content-encoding", "identity").lower() != "identity":
                    raise ConversionError("Compressed HTTP responses are unsupported")
                if int(response.headers.get("content-length", "0")) > limit:
                    raise ConversionError("Remote file exceeds byte limit")
                chunks = bytearray()
                for chunk in response.iter_raw(chunk_size=65536):
                    chunks.extend(chunk)
                    if len(chunks) > limit:
                        raise ConversionError("Remote file exceeds decoded byte limit")
                return bytes(chunks)
    raise ConversionError("Too many redirects")


def acquire(
    inputs: list[str],
    limits: Limits | None = None,
    revision: str | None = None,
    getter: Callable[[str, int], bytes] = fetch,
) -> list[Source]:
    """Collect deterministic file order; refuse incomplete repository listings."""
    limits = limits or Limits()
    sources: list[Source] = []
    total = 0
    seen: set[str] = set()

    def add(name: str, origin: str, data: bytes, rev: str | None = None) -> None:
        nonlocal total
        if origin in seen:
            return
        if len(sources) >= limits.max_files:
            raise ConversionError("File count limit exceeded")
        total += len(data)
        if len(data) > limits.max_file_bytes or total > limits.max_total_bytes:
            raise ConversionError("Source byte limit exceeded")
        seen.add(origin)
        sources.append(Source(name, origin, data, rev))

    def download(name: str, url: str, rev: str | None = None) -> None:
        if url in seen:
            return
        if len(sources) >= limits.max_files:
            raise ConversionError("File count limit exceeded")
        add(name, url, getter(url, min(limits.max_file_bytes, limits.max_total_bytes - total)), rev)

    def api(url: str) -> dict[str, object]:
        value = json.loads(getter(url, min(limits.max_file_bytes, 16 * 1024 * 1024)))
        if not isinstance(value, dict):
            raise ConversionError("Invalid repository API response")
        return value

    def repository(url: str) -> bool:
        parsed = urlsplit(url)
        parts = [unquote(x) for x in parsed.path.strip("/").split("/")]
        if parsed.hostname == "github.com":
            if len(parts) < 2:
                raise ConversionError("GitHub URL needs owner/repository")
            owner, repo = parts[:2]
            repo = repo.removesuffix(".git")
            base = f"https://api.github.com/repos/{quote(owner)}/{quote(repo)}"
            ref, prefix, single = revision or "HEAD", "", False
            if len(parts) > 2:
                if parts[2] not in {"tree", "blob"} or len(parts) < 4:
                    raise ConversionError("Use a GitHub repository, tree or blob URL")
                ref = revision or parts[3]
                prefix = "/".join(parts[4:])
                single = parts[2] == "blob"
            commit = api(f"{base}/commits/{quote(ref, safe='')}")
            sha = str(commit["sha"])
            raw = f"https://raw.githubusercontent.com/{quote(owner)}/{quote(repo)}/{sha}"
            if single:
                download(prefix, f"{raw}/{quote(prefix, safe='/')}", sha)
                return True
            tree = api(f"{base}/git/trees/{sha}?recursive=1")
            if tree.get("truncated"):
                raise ConversionError("GitHub tree is truncated; select a smaller/local source")
            entries = tree.get("tree")
            if not isinstance(entries, list):
                raise ConversionError("Missing GitHub file tree")
            for entry in sorted(entries, key=lambda e: e["path"]):
                path = entry["path"]
                if entry["type"] != "blob" or entry["mode"] == "120000":
                    continue
                if prefix and not path.startswith(prefix.rstrip("/") + "/"):
                    continue
                if Path(path).suffix.lower() in SUFFIXES:
                    download(path, f"{raw}/{quote(path, safe='/')}", sha)
            return True
        if parsed.hostname == "huggingface.co":
            kind = "datasets" if parts[0] == "datasets" else "models"
            offset = 1 if kind == "datasets" else 0
            if len(parts) < offset + 2:
                raise ConversionError("Hugging Face URL needs namespace/repository")
            repo = "/".join(parts[offset : offset + 2])
            rest = parts[offset + 2 :]
            ref, prefix, single = revision or "main", "", False
            if rest:
                if len(rest) < 2 or rest[0] not in {"tree", "blob", "resolve"}:
                    raise ConversionError(
                        "Use a Hugging Face repository, tree, blob or resolve URL"
                    )
                ref = revision or rest[1]
                prefix = "/".join(rest[2:])
                single = rest[0] in {"blob", "resolve"}
            info = api(
                f"https://huggingface.co/api/{kind}/{quote(repo, safe='/')}/revision/"
                f"{quote(ref, safe='')}"
            )
            sha = str(info["sha"])
            base = f"https://huggingface.co/{'datasets/' if kind == 'datasets' else ''}{repo}"
            raw = f"{base}/resolve/{sha}"
            if single:
                download(prefix, f"{raw}/{quote(prefix, safe='/')}", sha)
                return True
            siblings = info.get("siblings")
            if not isinstance(siblings, list):
                raise ConversionError("Missing Hugging Face repository file inventory")
            for entry in sorted(siblings, key=lambda e: e["rfilename"]):
                path = entry["rfilename"]
                if prefix and not path.startswith(prefix.rstrip("/") + "/"):
                    continue
                if Path(path).suffix.lower() in SUFFIXES:
                    download(path, f"{raw}/{quote(path, safe='/')}", sha)
            return True
        return False

    for value in inputs:
        if "://" in value:
            parsed = urlsplit(value)
            if parsed.scheme != "https" or parsed.username or parsed.password:
                raise ConversionError("Use a local path or credential-free HTTPS URL")
            if parsed.query or parsed.fragment:
                raise ConversionError("Use canonical URLs without query strings or fragments")
            if not repository(value):
                download(Path(unquote(parsed.path)).name or "document.xml", value)
        else:
            path = Path(value).expanduser()
            if path.is_symlink():
                raise ConversionError("Symlink input is not accepted")
            path = path.resolve(strict=True)
            files = sorted(path.rglob("*")) if path.is_dir() else [path]
            for file in files:
                if file.is_symlink() or not file.is_file():
                    continue
                if path.is_dir() and (
                    file.suffix.lower() not in SUFFIXES
                    or any(p.startswith(".") for p in file.relative_to(path).parts)
                ):
                    continue
                if len(sources) >= limits.max_files or file.stat().st_size > limits.max_file_bytes:
                    raise ConversionError("Local source limit exceeded")
                with file.open("rb") as stream:
                    data = stream.read(limits.max_file_bytes + 1)
                add(
                    str(file.relative_to(path)) if path.is_dir() else file.name, file.as_uri(), data
                )
    if not sources:
        raise ConversionError("No candidate source files found")
    return sources
