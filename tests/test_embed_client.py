"""Tests for tools/embed-client/client.py.

Uses unittest.mock to patch urllib calls — no live Alcove server required.
"""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "embed-client" / "client.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("embed_client", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("embed_client", mod)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def ec():
    return _load_module()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _mock_response(payload: dict | list, status: int = 200) -> MagicMock:
    """Build a mock urllib response object."""
    body = json.dumps(payload).encode("utf-8")
    resp = MagicMock()
    resp.read.return_value = body
    resp.status = status
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── Constructor ───────────────────────────────────────────────────────────────


def test_default_base_url(ec):
    client = ec.AlcoveClient()
    assert client.base_url == "http://localhost:8000"


def test_custom_base_url_strips_trailing_slash(ec):
    client = ec.AlcoveClient("http://localhost:9000/")
    assert client.base_url == "http://localhost:9000"


def test_api_key_stored(ec):
    client = ec.AlcoveClient(api_key="secret")
    assert client._api_key == "secret"


# ── health() ─────────────────────────────────────────────────────────────────


def test_health_returns_dict(ec):
    with patch("urllib.request.urlopen", return_value=_mock_response({"ok": True})):
        client = ec.AlcoveClient()
        result = client.health()
    assert result["ok"] is True


# ── search() ─────────────────────────────────────────────────────────────────


_SEARCH_RESPONSE = {
    "documents": [["doc one text", "doc two text"]],
    "metadatas": [[
        {"source": "file.pdf", "collection": "default"},
        {"source": "other.txt", "collection": "default"},
    ]],
    "distances": [[0.1, 0.2]],
}


def test_search_returns_result_list(ec):
    with patch("urllib.request.urlopen", return_value=_mock_response(_SEARCH_RESPONSE)):
        client = ec.AlcoveClient()
        results = client.search("test query", k=2)
    assert len(results) == 2


def test_search_result_fields(ec):
    with patch("urllib.request.urlopen", return_value=_mock_response(_SEARCH_RESPONSE)):
        client = ec.AlcoveClient()
        results = client.search("test query")
    r = results[0]
    assert r["text"] == "doc one text"
    assert r["source"] == "file.pdf"
    assert r["collection"] == "default"
    assert 0 <= r["score"] <= 1.0


def test_search_empty_results(ec):
    empty = {"documents": [[]], "metadatas": [[]], "distances": [[]]}
    with patch("urllib.request.urlopen", return_value=_mock_response(empty)):
        client = ec.AlcoveClient()
        results = client.search("nothing")
    assert results == []


# ── collections() ────────────────────────────────────────────────────────────


def test_collections_returns_list(ec):
    payload = [{"name": "default", "count": 10}]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        client = ec.AlcoveClient()
        colls = client.collections()
    assert colls == payload


# ── ingest_file() ────────────────────────────────────────────────────────────


def test_ingest_file(ec, tmp_path):
    txt = tmp_path / "sample.txt"
    txt.write_text("Hello world")
    payload = [{"filename": "sample.txt", "chunks": 1, "status": "indexed"}]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        client = ec.AlcoveClient()
        result = client.ingest_file(txt)
    assert result == payload


def test_ingest_files_multiple(ec, tmp_path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("aaa")
    f2.write_text("bbb")
    payload = [
        {"filename": "a.txt", "chunks": 1, "status": "indexed"},
        {"filename": "b.txt", "chunks": 1, "status": "indexed"},
    ]
    with patch("urllib.request.urlopen", return_value=_mock_response(payload)):
        client = ec.AlcoveClient()
        result = client.ingest_files([f1, f2])
    assert len(result) == 2


# ── Error handling ────────────────────────────────────────────────────────────


def test_http_error_raises_alcove_error(ec):
    from urllib.error import HTTPError
    err = HTTPError(
        url="http://localhost:8000/health",
        code=500,
        msg="Internal Server Error",
        hdrs=None,
        fp=io.BytesIO(b"server broke"),
    )
    with patch("urllib.request.urlopen", side_effect=err):
        client = ec.AlcoveClient()
        with pytest.raises(ec.AlcoveError) as exc_info:
            client.health()
    assert exc_info.value.status == 500


def test_url_error_raises_alcove_error(ec):
    from urllib.error import URLError
    err = URLError(reason="Connection refused")
    with patch("urllib.request.urlopen", side_effect=err):
        client = ec.AlcoveClient()
        with pytest.raises(ec.AlcoveError) as exc_info:
            client.health()
    assert exc_info.value.status == 0


# ── API key header ────────────────────────────────────────────────────────────


def test_api_key_sent_in_header(ec):
    captured_requests = []

    def fake_urlopen(req, timeout=None):
        captured_requests.append(req)
        return _mock_response({"ok": True})

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        client = ec.AlcoveClient(api_key="my-secret")
        client.health()

    req = captured_requests[0]
    assert req.get_header("Authorization") == "Bearer my-secret"
