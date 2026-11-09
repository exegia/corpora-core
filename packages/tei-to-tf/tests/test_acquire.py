import json
import socket

import pytest

from tei_to_tf.acquire import Limits, acquire, public_url
from tei_to_tf.model import ConversionError


class Remote:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, url, limit):
        self.calls.append(url)
        value = self.responses[url]
        data = value if isinstance(value, bytes) else json.dumps(value).encode()
        if len(data) > limit:
            raise ConversionError("limit")
        return data


def test_local_directory_sorted_skips_symlinks_and_hidden(tmp_path):
    (tmp_path / "b.xml").write_text("<b/>")
    (tmp_path / "a.tei").write_text("<a/>")
    (tmp_path / ".secret.xml").write_text("secret")
    (tmp_path / "link.xml").symlink_to(tmp_path / "b.xml")
    (tmp_path / "image.png").write_bytes(b"not xml")
    assert [x.name for x in acquire([str(tmp_path)])] == ["a.tei", "b.xml"]
    with pytest.raises(ConversionError, match="limit"):
        acquire([str(tmp_path)], Limits(max_files=1))


def test_direct_file_and_limits():
    url = "https://example.org/document.xml"
    remote = Remote({url: b"<TEI/>"})
    assert acquire([url], getter=remote)[0].data == b"<TEI/>"
    with pytest.raises(ConversionError):
        acquire([url], Limits(max_file_bytes=3), getter=remote)
    assert len(acquire([url, url], getter=remote)) == 1


@pytest.mark.parametrize("suffix", ["", "/tree/main/docs"])
def test_github_repository_pinned_and_filtered(suffix):
    base = "https://api.github.com/repos/owner/repo"
    ref = "main" if suffix else "HEAD"
    remote = Remote(
        {
            f"{base}/commits/{ref}": {"sha": "abc123"},
            f"{base}/git/trees/abc123?recursive=1": {
                "truncated": False,
                "tree": [
                    {"path": "docs/a.xml", "type": "blob", "mode": "100644"},
                    {"path": "docs/link.xml", "type": "blob", "mode": "120000"},
                    {"path": "image.png", "type": "blob", "mode": "100644"},
                ],
            },
            "https://raw.githubusercontent.com/owner/repo/abc123/docs/a.xml": b"<TEI/>",
        }
    )
    result = acquire(["https://github.com/owner/repo" + suffix], getter=remote)
    assert len(result) == 1 and result[0].revision == "abc123"
    assert result[0].origin.endswith("/abc123/docs/a.xml")


def test_github_blob_and_slash_revision():
    remote = Remote(
        {
            "https://api.github.com/repos/o/r/commits/feature%2Ftei": {"sha": "fixed"},
            "https://raw.githubusercontent.com/o/r/fixed/a.xml": b"<TEI/>",
        }
    )
    result = acquire(
        ["https://github.com/o/r/blob/main/a.xml"], revision="feature/tei", getter=remote
    )
    assert result[0].name == "a.xml"


def test_github_truncation_is_not_partial_success():
    remote = Remote(
        {
            "https://api.github.com/repos/o/r/commits/HEAD": {"sha": "fixed"},
            "https://api.github.com/repos/o/r/git/trees/fixed?recursive=1": {
                "truncated": True,
                "tree": [],
            },
        }
    )
    with pytest.raises(ConversionError, match="truncated"):
        acquire(["https://github.com/o/r"], getter=remote)


@pytest.mark.parametrize(
    "suffix", ["", "/tree/main/docs", "/blob/main/docs/a.xml", "/resolve/main/docs/a.xml"]
)
def test_huggingface_repositories_and_file_urls(suffix):
    remote = Remote(
        {
            "https://huggingface.co/api/datasets/o/r/revision/main": {
                "sha": "fixed",
                "siblings": [{"rfilename": "docs/a.xml"}, {"rfilename": "a.bin"}],
            },
            "https://huggingface.co/datasets/o/r/resolve/fixed/docs/a.xml": b"<TEI/>",
        }
    )
    result = acquire(["https://huggingface.co/datasets/o/r" + suffix], getter=remote)
    assert result[0].revision == "fixed"
    assert len(result) == 1


def test_missing_hf_inventory_refused():
    remote = Remote({"https://huggingface.co/api/datasets/o/r/revision/main": {"sha": "fixed"}})
    with pytest.raises(ConversionError, match="inventory"):
        acquire(["https://huggingface.co/datasets/o/r"], getter=remote)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/a.xml",
        "https://user:password@example.org/a.xml",
        "https://example.org/a.xml?token=secret",
        "file:///etc/passwd",
    ],
)
def test_unsupported_remote_locations(url):
    with pytest.raises(ConversionError):
        acquire([url], getter=Remote({}))


def test_private_address_rejected(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("127.0.0.1", 443))])
    with pytest.raises(ConversionError, match="Private"):
        public_url("https://example.org/a.xml")
