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
    _mod_key = "embed_client_test_module"
    spec = importlib.util.spec_from_file_location(_mod_key, _MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {_MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_mod_key] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(_mod_key, None)
        raise
    return mod


@pytest.fixture(scope="module")
def ec():
    _mod_key = "embed_client_test_module"
    prev = sys.modules.get(_mod_key)
    mod = _load_module()
    yield mod
    if prev is None:
        sys.modules.pop(_mod_key, None)
    else:
        sys.modules[_mod_key] = prev


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


def test_base_url_from_env(ec, monkeypatch):
    monkeypatch.setenv("ALCOVE_URL", "http://remotehost:9999")
    client = ec.AlcoveClient()
    assert client.base_url == "http://remotehost:9999"


def test_api_key_from_env(ec, monkeypatch):
    monkeypatch.setenv("ALCOVE_API_KEY", "envkey")
    client = ec.AlcoveClient()
    assert client._api_key == "envkey"


def test_invalid_scheme_raises(ec):
    with pytest.raises(ValueError, match="http or https"):
        ec.AlcoveClient("ftp://localhost:21")


def test_missing_scheme_raises(ec):
    with pytest.raises(ValueError, match="http or https"):
        ec.AlcoveClient("localhost:8000")


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


# ── Multipart upload guards ───────────────────────────────────────────────────


def test_ingest_oversized_file_raises(ec, tmp_path):
    """Files exceeding the 25 MB cap must raise before sending."""
    big_file = tmp_path / "huge.bin"
    # Write 26 MB of zeros
    big_file.write_bytes(b"\x00" * (26 * 1024 * 1024))
    client = ec.AlcoveClient()
    with pytest.raises(ValueError, match="25 MB"):
        client.ingest_file(big_file)


def test_ingest_filename_special_chars_escaped(ec, tmp_path):
    """Filenames with special chars must be sanitised in the Content-Disposition header.

    We simulate a filename with a backslash (valid on POSIX, triggers the
    escape path) by patching Path.name after writing the file.
    """
    normal_file = tmp_path / "normal.txt"
    normal_file.write_text("content")

    from unittest.mock import PropertyMock

    payload = [{"filename": "back\\slash.txt", "chunks": 1, "status": "indexed"}]
    captured_bodies: list[bytes] = []

    def fake_urlopen(req, timeout=None):
        captured_bodies.append(req.data)
        return _mock_response(payload)

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        with patch.object(type(normal_file), "name", new_callable=PropertyMock, return_value='back\\slash.txt'):
            client = ec.AlcoveClient()
            client.ingest_file(normal_file)

    assert len(captured_bodies) == 1
    # backslash must be doubled in the header
    assert b"back\\\\slash.txt" in captured_bodies[0]
