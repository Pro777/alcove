from __future__ import annotations

import collections as _collections
import html
import json
import atexit
import os
import re
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True))
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.templating import Jinja2Templates
import uvicorn

from alcove.web import TEMPLATES_DIR, STATIC_DIR
from .retriever import query_hybrid, query_keyword, query_text

app = FastAPI(title="Alcove")

# ---------------------------------------------------------------------------
# Optional telemetry (activated by ALCOVE_ACCESS_LOG env var)
# ---------------------------------------------------------------------------
_ACCESS_LOG_PATH = os.environ.get("ALCOVE_ACCESS_LOG")
_METRICS_ENABLED = _ACCESS_LOG_PATH is not None

if _METRICS_ENABLED:
    _start_time = time.monotonic()
    _total_requests = 0
    _active_requests = 0
    _error_count_4xx = 0
    _error_count_5xx = 0
    _largest_view_bytes = 0
    _recent_times: _collections.deque = _collections.deque(maxlen=100)
    _access_log_file = None

    def _get_access_log():
        global _access_log_file
        if _access_log_file is None:
            log_path = Path(_ACCESS_LOG_PATH)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            _access_log_file = open(log_path, "a", encoding="utf-8")  # noqa: SIM115
            atexit.register(_close_access_log)
        return _access_log_file

    def _close_access_log():
        global _access_log_file
        if _access_log_file is not None:
            try:
                _access_log_file.close()
            except Exception:
                pass
            _access_log_file = None

    def _write_log(entry: dict):
        try:
            f = _get_access_log()
            f.write(json.dumps(entry) + "\n")
            f.flush()
        except Exception:
            pass

    @app.middleware("http")
    async def _telemetry_middleware(request: Request, call_next):
        global _total_requests, _active_requests, _error_count_4xx, _error_count_5xx, _largest_view_bytes

        _total_requests += 1
        _active_requests += 1
        t0 = time.monotonic()
        status = 500
        doc_bytes = None

        try:
            response = await call_next(request)
            status = response.status_code

            if request.url.path == "/view" and 200 <= status < 300:
                body_parts = []
                async for chunk in response.body_iterator:
                    if isinstance(chunk, bytes):
                        body_parts.append(chunk)
                    else:
                        body_parts.append(chunk.encode("utf-8"))
                body_bytes = b"".join(body_parts)
                doc_bytes = len(body_bytes)
                if doc_bytes > _largest_view_bytes:
                    _largest_view_bytes = doc_bytes

                from starlette.responses import Response as StarletteResponse
                response = StarletteResponse(
                    content=body_bytes,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )

            return response
        except Exception as exc:
            status = 500
            _write_log({
                "ts": datetime.now(timezone.utc).isoformat(),
                "method": request.method,
                "path": request.url.path,
                "status": 500,
                "ms": round((time.monotonic() - t0) * 1000, 1),
                "error": type(exc).__name__,
            })
            raise
        finally:
            elapsed_ms = round((time.monotonic() - t0) * 1000, 1)
            _active_requests -= 1
            _recent_times.append(elapsed_ms)

            if 400 <= status < 500:
                _error_count_4xx += 1
            elif status >= 500:
                _error_count_5xx += 1

            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "ms": elapsed_ms,
            }
            if doc_bytes is not None:
                entry["doc_bytes"] = doc_bytes
            _write_log(entry)

    @app.get("/metrics")
    def metrics():
        uptime_s = round(time.monotonic() - _start_time, 1)
        avg_ms = round(sum(_recent_times) / len(_recent_times), 1) if _recent_times else 0.0
        return {
            "total_requests": _total_requests,
            "active_requests": _active_requests,
            "avg_response_time_ms": avg_ms,
            "error_count_4xx": _error_count_4xx,
            "error_count_5xx": _error_count_5xx,
            "largest_view_bytes": _largest_view_bytes,
            "uptime_seconds": uptime_s,
        }

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["alcove_title"] = os.environ.get("ALCOVE_TITLE", "Alcove")
templates.env.globals["alcove_tagline"] = os.environ.get("ALCOVE_TAGLINE", "Document Search")
templates.env.globals["alcove_logo_text"] = os.environ.get("ALCOVE_LOGO_TEXT", "A")
templates.env.globals["alcove_accent_color"] = os.environ.get("ALCOVE_ACCENT_COLOR", "")
templates.env.globals["alcove_accent_color_light"] = os.environ.get("ALCOVE_ACCENT_COLOR_LIGHT", "")

_default_footer = f"{os.environ.get('ALCOVE_TITLE', 'Alcove')} \u00a9 {datetime.now().year}"
templates.env.globals["alcove_footer_text"] = os.environ.get("ALCOVE_FOOTER_TEXT", _default_footer)

# Mount raw document directory so users can click through to source files
_raw_dir = os.getenv("RAW_DIR", "data/raw")
if Path(_raw_dir).is_dir():
    app.mount("/files", StaticFiles(directory=_raw_dir), name="files")

SUPPORTED_EXTENSIONS = {
    ".txt", ".pdf", ".epub",
    ".html", ".htm",
    ".md", ".rst",
    ".csv", ".tsv",
    ".json", ".jsonl",
    ".docx",
}


class QueryIn(BaseModel):
    query: str
    k: int = 3
    collections: Optional[List[str]] = None
    mode: str = "semantic"


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def root(request: Request):
    from alcove.index.backend import get_backend
    from alcove.index.embedder import get_embedder
    try:
        backend = get_backend(get_embedder())
        doc_count = backend.count()
    except Exception:
        doc_count = 0
    return templates.TemplateResponse("search.html", {"request": request, "doc_count": doc_count})


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", k: int = 20, collections: str = "", mode: str = "semantic"):
    _COLL_RE = re.compile(r"^[a-zA-Z0-9_\-\.]{1,128}$")
    coll_list: Optional[List[str]] = None
    if collections.strip():
        tokens = [c.strip() for c in collections.split(",") if c.strip()]
        invalid = [t for t in tokens if not _COLL_RE.match(t)]
        if invalid:
            return JSONResponse(
                status_code=422,
                content={"detail": f"Invalid collection name(s): {invalid}"},
            )
        coll_list = tokens
    results: list = []
    search_error = False
    if q.strip():
        try:
            raw = _dispatch_query(q, k, mode=mode, collections=coll_list)
            documents = raw.get("documents", [[]])[0]
            metadatas = raw.get("metadatas", [[]])[0]
            distances = raw.get("distances", [[]])[0]

            for doc, meta, dist in zip(documents, metadatas, distances, strict=True):
                snippets_raw = _extract_snippets(doc, q)
                snippets_html = [_highlight(html.escape(s), q) for s in snippets_raw]

                full_escaped = html.escape(doc)
                full_highlighted = _highlight(full_escaped, q)

                source = meta.get("source", "unknown") if isinstance(meta, dict) else "unknown"
                results.append({
                    "snippets": snippets_html,
                    "full_text": full_highlighted,
                    "source": source,
                    "source_fname": Path(source).name,
                    "collection": meta.get("collection", "default") if isinstance(meta, dict) else "default",
                    "score": round(1.0 / (1.0 + dist), 3) if dist >= 0 else 0.0,
                })
        except Exception:
            traceback.print_exc()
            search_error = True

    return templates.TemplateResponse(
        "results.html",
        {"request": request, "query": q, "results": results, "search_error": search_error, "mode": mode},
    )


VIEW_MAX_LINES = int(os.getenv("VIEW_MAX_LINES", "2000"))
VIEW_MAX_BYTES = int(os.getenv("VIEW_MAX_BYTES", str(10 * 1024 * 1024)))  # 10 MB
VIEW_TIMEOUT_SECS = float(os.getenv("VIEW_TIMEOUT_SECS", "10"))


@app.get("/view", response_class=HTMLResponse)
def view_document(request: Request, source: str = "", q: str = ""):
    """Render a document with line numbers and optional search highlighting."""
    t0 = time.monotonic()
    raw_dir = os.getenv("RAW_DIR", "data/raw")
    clean_dir = os.getenv("CLEAN_DIR", "data/clean")

    ctx = {"request": request, "filename": source, "lines": [], "query": q,
           "error": None, "truncated": False, "total_lines": 0, "shown_lines": 0}

    doc_path = None
    for base in [clean_dir, raw_dir]:
        base_resolved = Path(base).resolve()
        candidate = (Path(base) / source).resolve()
        # Path traversal containment check
        if not str(candidate).startswith(str(base_resolved) + os.sep) and candidate != base_resolved:
            raise HTTPException(status_code=403, detail="Access denied")
        if candidate.exists() and candidate.is_file():
            doc_path = candidate
            break

    if not doc_path:
        ctx["error"] = "File not found"
        return templates.TemplateResponse("view.html", ctx)

    file_size = doc_path.stat().st_size
    if file_size > VIEW_MAX_BYTES:
        ctx["error"] = (
            f"Document too large to display ({file_size:,} bytes, "
            f"limit is {VIEW_MAX_BYTES:,} bytes)"
        )
        return templates.TemplateResponse("view.html", ctx)

    try:
        if doc_path.suffix.lower() == ".pdf":
            from alcove.ingest.extractors import extract_pdf
            text = extract_pdf(doc_path)
        elif doc_path.suffix.lower() == ".docx":
            from alcove.ingest.extractors import extract_docx
            text = extract_docx(doc_path)
        else:
            text = doc_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        ctx["error"] = str(e)
        return templates.TemplateResponse("view.html", ctx)

    elapsed = time.monotonic() - t0
    if elapsed > VIEW_TIMEOUT_SECS:
        ctx["error"] = f"Document loading took too long ({elapsed:.1f}s)"
        return templates.TemplateResponse("view.html", ctx)

    raw_lines = text.splitlines()
    total = len(raw_lines)
    show = min(total, VIEW_MAX_LINES)
    truncated = total > VIEW_MAX_LINES

    lines = []
    for i, line in enumerate(raw_lines[:show], 1):
        escaped = html.escape(line) if line.strip() else ""
        highlighted = _highlight(escaped, q) if q and escaped else escaped
        lines.append({"num": i, "text": highlighted, "blank": not line.strip()})

    ctx["lines"] = lines
    ctx["truncated"] = truncated
    ctx["total_lines"] = total
    ctx["shown_lines"] = show

    return templates.TemplateResponse("view.html", ctx)


@app.post("/query")
def query(inp: QueryIn):
    return _dispatch_query(inp.query, inp.k, mode=inp.mode, collections=inp.collections)


@app.post("/ingest")
async def ingest(
    files: list[UploadFile] = File(...),
    collection: str = Query(
        "default",
        max_length=128,
        pattern=r"^[a-zA-Z0-9_\-\.]+$",
        description="Target collection name",
    ),
):
    raw_dir = os.getenv("RAW_DIR", "data/raw")
    chunks_file = os.getenv("CHUNKS_FILE", "data/processed/chunks.jsonl")
    raw_path = Path(raw_dir)
    raw_path.mkdir(parents=True, exist_ok=True)

    saved_files: list = []
    skipped_files: list = []
    for f in files:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            skipped_files.append({
                "filename": f.filename or "(unknown)",
                "reason": f"Unsupported format: {ext or '(none)'}",
            })
            continue
        safe_name = Path(f.filename or "upload").name  # strip directory traversal
        dest = raw_path / safe_name
        content = await f.read()
        dest.write_bytes(content)
        saved_files.append(safe_name)

    # Only run pipelines if we have files to process
    if saved_files:
        # Run ingest pipeline (extract + chunk)
        from alcove.ingest.pipeline import run as ingest_run

        ingest_run(raw_dir=raw_dir, out_file=chunks_file)

        # Count chunks per uploaded file from chunks.jsonl
        chunk_counts: dict = {}
        chunks_path = Path(chunks_file)
        if chunks_path.exists():
            with chunks_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    rec = json.loads(line)
                    source = rec.get("source", "")
                    fname = Path(source).name
                    if fname in saved_files:
                        chunk_counts[fname] = chunk_counts.get(fname, 0) + 1

        # Run index pipeline with collection name
        from alcove.index.pipeline import run as index_run

        index_run(chunks_file=chunks_file, collection=collection)
    else:
        chunk_counts = {}

    # Build response: indexed files + skipped files
    response = []
    for fname in saved_files:
        response.append({
            "filename": fname,
            "chunks": chunk_counts.get(fname, 0),
            "status": "indexed",
            "collection": collection,
        })
    for skipped in skipped_files:
        response.append({
            "filename": skipped["filename"],
            "chunks": 0,
            "status": "skipped",
            "reason": skipped["reason"],
        })

    return JSONResponse(content=response)


@app.get("/collections")
def list_collections():
    """Return all named collections with their document counts."""
    from alcove.index.backend import get_backend
    from alcove.index.embedder import get_embedder
    try:
        backend = get_backend(get_embedder())
        return backend.list_collections()
    except Exception:
        return []


def _dispatch_query(
    q: str,
    k: int,
    mode: str = "semantic",
    collections: Optional[List[str]] = None,
) -> dict:
    """Route to the correct retriever based on search mode."""
    if mode == "keyword":
        return query_keyword(q, n_results=k)
    elif mode == "hybrid":
        return query_hybrid(q, n_results=k, collections=collections)
    else:
        return query_text(q, n_results=k, collections=collections)


def _extract_snippets(
    text: str, query: str, max_snippets: int = 3, context_chars: int = 150
) -> list[str]:
    if not text:
        return []

    terms = [t for t in query.split() if len(t) >= 2]

    if not terms:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences[:2] if s.strip()]

    positions: list[tuple[int, int]] = []
    text_lower = text.lower()
    for term in terms:
        term_lower = term.lower()
        start = 0
        while True:
            idx = text_lower.find(term_lower, start)
            if idx == -1:
                break
            positions.append((idx, idx + len(term_lower)))
            start = idx + 1

    if not positions:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        return [s.strip() for s in sentences[:2] if s.strip()]

    positions.sort(key=lambda p: p[0])

    windows: list[tuple[int, int]] = []
    for match_start, match_end in positions:
        win_start = max(0, match_start - context_chars)
        win_end = min(len(text), match_end + context_chars)
        windows.append((win_start, win_end))

    merged: list[tuple[int, int]] = []
    for win_start, win_end in windows:
        if merged and win_start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], win_end))
        else:
            merged.append((win_start, win_end))

    snippets: list[str] = []
    for win_start, win_end in merged[:max_snippets]:
        chunk = text[win_start:win_end].strip()
        if not chunk:
            continue
        prefix = "..." if win_start > 0 else ""
        suffix = "..." if win_end < len(text) else ""
        snippets.append(prefix + chunk + suffix)

    return snippets if snippets else [text[:300].strip()]


_HIGHLIGHT_MAX_LEN = 50_000

def _highlight(escaped_text: str, query: str) -> str:
    """Insert <mark> tags around query terms in already-HTML-escaped text."""
    if len(escaped_text) > _HIGHLIGHT_MAX_LEN:
        return escaped_text
    terms = [t for t in query.split() if len(t) >= 2]
    if not terms:
        return escaped_text
    combined = "|".join(re.escape(t) for t in terms)
    pattern = re.compile(combined, re.IGNORECASE)
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped_text)


if __name__ == "__main__":
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
