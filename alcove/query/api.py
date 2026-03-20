from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Query, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.templating import Jinja2Templates
import uvicorn

from alcove.web import TEMPLATES_DIR, STATIC_DIR
from .retriever import query_hybrid, query_keyword, query_text

app = FastAPI(title="Alcove")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _root_path() -> str:
    """Return the URL prefix configured via ALCOVE_ROOT_PATH (e.g. '/demos')."""
    raw = os.getenv("ALCOVE_ROOT_PATH", "").strip().strip("/")
    return "" if not raw else "/" + raw


def _tpl(ctx: dict) -> dict:
    """Merge template context with the base_url global."""
    ctx.setdefault("base_url", _root_path())
    return ctx

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
    return templates.TemplateResponse("search.html", _tpl({"request": request, "doc_count": doc_count}))


@app.get("/demos", response_class=HTMLResponse)
def demos_index(request: Request):
    """Landing page listing all demo corpora with live/coming-soon status."""
    import json as _json

    demos_config_path = Path(__file__).resolve().parents[1] / "web" / "demos.json"
    try:
        raw_demos: list[dict] = _json.loads(demos_config_path.read_text(encoding="utf-8"))
    except Exception:
        raw_demos = []

    # Resolve live collections from the backend
    live_collections: set[str] = set()
    try:
        from alcove.index.backend import get_backend
        from alcove.index.embedder import get_embedder
        backend = get_backend(get_embedder())
        for col in backend.list_collections():
            name = col["name"] if isinstance(col, dict) else str(col)
            live_collections.add(name)
    except Exception:
        pass

    demos = []
    for d in raw_demos:
        col = d.get("collection", "")
        is_live = col in live_collections
        doc_count: Optional[int] = None
        if is_live:
            try:
                from alcove.index.backend import list_chromadb_collections
                for c in list_chromadb_collections():
                    if c["name"] == col:
                        doc_count = c["count"]
                        break
            except Exception:
                pass
        demos.append({
            **d,
            "status": "live" if is_live else "coming_soon",
            "doc_count": doc_count,
        })

    return templates.TemplateResponse(
        "demos.html",
        _tpl({
            "request": request,
            "demos": demos,
        }),
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", k: int = 5, collections: str = "", mode: str = "semantic"):
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
    if q.strip():
        raw = _dispatch_query(q, k, mode=mode, collections=coll_list)
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            escaped = html.escape(doc)
            highlighted = _highlight(escaped, q)
            results.append({
                "text": highlighted,
                "source": meta.get("source", "unknown") if isinstance(meta, dict) else "unknown",
                "collection": meta.get("collection", "default") if isinstance(meta, dict) else "default",
                "score": round(1.0 - dist, 3) if dist <= 1.0 else round(dist, 3),
            })

    return templates.TemplateResponse(
        "results.html",
        _tpl({"request": request, "query": q, "results": results}),
    )


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
    if os.getenv("ALCOVE_DEMO_ROOT", ""):
        return JSONResponse(
            status_code=403,
            content={"detail": "Ingest is disabled in demo/read-only mode."},
        )
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


def _highlight(escaped_text: str, query: str) -> str:
    """Insert <mark> tags around query terms in already-HTML-escaped text."""
    terms = [t for t in query.split() if len(t) >= 2]
    result = escaped_text
    for term in terms:
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        result = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", result)
    return result


if __name__ == "__main__":
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
