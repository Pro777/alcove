#!/usr/bin/env python3
"""Python SDK for embedding Alcove in host applications.

Provides a thin, requests-optional HTTP client for the Alcove search and ingest
API. Uses ``urllib`` from the standard library when ``requests`` is not installed,
so it works with a plain Python install.

Usage::

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "alcove_embed_client", "tools/embed-client/client.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    AlcoveClient = mod.AlcoveClient

    alcove = AlcoveClient("http://localhost:8000")

    # Search
    results = alcove.search("medieval manuscripts", k=5)
    for r in results:
        print(r["score"], r["source"], r["text"][:80])

    # Ingest a local file
    alcove.ingest_file("path/to/document.pdf")

    # Health check
    assert alcove.health()["ok"] is True
"""
from __future__ import annotations

import io
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib import parse, request, error as urllib_error


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AlcoveError(Exception):
    """Raised when the Alcove server returns a non-2xx response."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AlcoveClient:
    """HTTP client for the Alcove search and ingest API.

    Args:
        base_url: Base URL of the Alcove server (e.g. ``"http://localhost:8000"``).
            Trailing slashes are stripped.
        timeout: Request timeout in seconds (default: 30).
        api_key: Optional bearer token sent as ``Authorization: Bearer <key>``.
            Alcove itself does not enforce API keys; pass one if a reverse proxy
            does.
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: int = 30,
        api_key: str | None = None,
    ) -> None:
        raw = (base_url or os.environ.get("ALCOVE_URL", "http://localhost:8000")).rstrip("/")
        _parsed = parse.urlparse(raw)
        if _parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"base_url must use http or https scheme, got: {raw!r}"
            )
        if not _parsed.netloc:
            raise ValueError(f"base_url must include a host, got: {raw!r}")
        self.base_url = raw
        self.timeout = timeout
        self._api_key = api_key or os.environ.get("ALCOVE_API_KEY")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        """Return the server health response (``{"ok": True}``)."""
        return self._get("/health")

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        collections: list[str] | None = None,
        mode: str = "semantic",
    ) -> list[dict[str, Any]]:
        """Semantic, keyword, or hybrid search.

        Args:
            query: Natural-language search string.
            k: Number of results to return (default: 5).
            collections: Optional list of collection names to restrict the search.
                When ``None``, all collections are searched.
            mode: ``"semantic"`` (default), ``"keyword"``, or ``"hybrid"``.

        Returns:
            List of result dicts with keys ``text``, ``source``, ``collection``,
            and ``score``.
        """
        payload: dict[str, Any] = {"query": query, "k": k}
        if mode != "semantic":
            payload["mode"] = mode
        if collections:
            payload["collections"] = collections
        raw = self._post_json("/query", payload)
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        if not (len(documents) == len(metadatas) == len(distances)):
            raise AlcoveError(
                200,
                f"Malformed /query response: array lengths differ "
                f"(documents={len(documents)}, metadatas={len(metadatas)}, "
                f"distances={len(distances)})",
            )
        results = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            results.append({
                "text": doc,
                "source": (meta or {}).get("source", ""),
                "collection": (meta or {}).get("collection", "default"),
                "score": round(1.0 - dist, 4) if dist <= 1.0 else round(dist, 4),
                "metadata": meta or {},
            })
        return results

    def ingest_file(
        self,
        path: str | Path,
        *,
        collection: str = "default",
    ) -> list[dict[str, Any]]:
        """Upload and index a single local file.

        Args:
            path: Path to the file to ingest (PDF, TXT, EPUB, HTML, MD, etc.).
            collection: Target collection name (default: ``"default"``).

        Returns:
            Ingest response list from the server.
        """
        return self._post_multipart(
            "/ingest",
            file_paths=[Path(path)],
            collection=collection,
        )

    def ingest_files(
        self,
        paths: list[str | Path],
        *,
        collection: str = "default",
    ) -> list[dict[str, Any]]:
        """Upload and index multiple local files in one request.

        Args:
            paths: Paths to files to ingest.
            collection: Target collection name.

        Returns:
            Ingest response list from the server.
        """
        return self._post_multipart(
            "/ingest",
            file_paths=[Path(p) for p in paths],
            collection=collection,
        )

    def collections(self) -> list[dict[str, Any]]:
        """Return all named collections with their document counts."""
        return self._get("/collections")

    # ------------------------------------------------------------------
    # Transport helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    def _get(self, path: str) -> Any:
        url = self.base_url + path
        req = request.Request(url, headers={**self._headers(), "Accept": "application/json"})
        return self._send(req)

    def _post_json(self, path: str, payload: dict[str, Any]) -> Any:
        url = self.base_url + path
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            url,
            data=body,
            headers={
                **self._headers(),
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        return self._send(req)

    def _post_multipart(
        self,
        path: str,
        *,
        file_paths: list[Path],
        collection: str,
    ) -> Any:
        boundary = b"alcoveclientboundary"
        _MAX_TOTAL_BYTES = 25 * 1024 * 1024  # 25 MB hard cap
        body_parts: list[bytes] = []
        total_bytes = 0

        for file_path in file_paths:
            mime_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
            file_bytes = file_path.read_bytes()
            total_bytes += len(file_bytes)
            if total_bytes > _MAX_TOTAL_BYTES:
                raise ValueError(
                    f"Total upload size exceeds {_MAX_TOTAL_BYTES // (1024 * 1024)} MB limit"
                )
            filename = (
                file_path.name
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\r", "")
                .replace("\n", "")
            )
            body_parts.append(
                b"--" + boundary + b"\r\n"
                b'Content-Disposition: form-data; name="files"; filename="'
                + filename.encode("utf-8")
                + b'"\r\n'
                + b"Content-Type: " + mime_type.encode("utf-8") + b"\r\n\r\n"
                + file_bytes
                + b"\r\n"
            )

        # Append collection field
        body_parts.append(
            b"--" + boundary + b"\r\n"
            b'Content-Disposition: form-data; name="collection"\r\n\r\n'
            + collection.encode("utf-8")
            + b"\r\n"
        )
        body_parts.append(b"--" + boundary + b"--\r\n")

        body = b"".join(body_parts)
        url = f"{self.base_url}{path}?collection={parse.quote(collection)}"
        req = request.Request(
            url,
            data=body,
            headers={
                **self._headers(),
                "Content-Type": f"multipart/form-data; boundary={boundary.decode()}",
                "Accept": "application/json",
            },
        )
        return self._send(req)

    def _send(self, req: request.Request) -> Any:
        try:
            with request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
        except urllib_error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise AlcoveError(exc.code, body) from exc
        except urllib_error.URLError as exc:
            raise AlcoveError(0, str(exc.reason)) from exc
