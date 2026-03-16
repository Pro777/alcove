from __future__ import annotations

import html
import json
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.templating import Jinja2Templates
import uvicorn

from alcove.web import TEMPLATES_DIR, STATIC_DIR
from .retriever import query_text

app = FastAPI(title="Alcove")

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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
def search(request: Request, q: str = "", k: int = 5):
    results: list = []
    if q.strip():
        raw = query_text(q, k)
        documents = raw.get("documents", [[]])[0]
        metadatas = raw.get("metadatas", [[]])[0]
        distances = raw.get("distances", [[]])[0]

        for doc, meta, dist in zip(documents, metadatas, distances):
            source = str((meta or {}).get("source", "unknown"))
            filename = Path(source).name or source
            excerpt = _excerpt_text(str(doc or ""), q)
            distance = float(dist or 0.0)
            results.append({
                "filename": _highlight(html.escape(filename), q),
                "source": source,
                "source_display": _highlight(html.escape(source), q),
                "text": _highlight(html.escape(excerpt), q),
                "href": f"/document?source={quote(source, safe='')}",
                "score": round(1.0 - distance, 3) if distance <= 1.0 else round(distance, 3),
            })

    return templates.TemplateResponse(
        "results.html",
        {"request": request, "query": q, "results": results},
    )


@app.get("/document")
def document(source: str):
    path = _resolve_indexed_source(source)
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.post("/query")
def query(inp: QueryIn):
    return query_text(inp.query, inp.k)


@app.post("/ingest")
async def ingest(files: list[UploadFile] = File(...)):
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

        # Run index pipeline
        from alcove.index.pipeline import run as index_run

        index_run(chunks_file=chunks_file)
    else:
        chunk_counts = {}

    # Build response: indexed files + skipped files
    response = []
    for fname in saved_files:
        response.append({
            "filename": fname,
            "chunks": chunk_counts.get(fname, 0),
            "status": "indexed",
        })
    for skipped in skipped_files:
        response.append({
            "filename": skipped["filename"],
            "chunks": 0,
            "status": "skipped",
            "reason": skipped["reason"],
        })

    return JSONResponse(content=response)


def _highlight(escaped_text: str, query: str) -> str:
    """Insert <mark> tags around query terms in already-HTML-escaped text."""
    terms = _query_terms(query)
    if not terms:
        return escaped_text

    pattern = re.compile(
        "|".join(re.escape(html.escape(term)) for term in terms),
        re.IGNORECASE,
    )
    return pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", escaped_text)


def _query_terms(query: str) -> list[str]:
    tokens = [token.strip() for token in re.split(r"\s+", query) if len(token.strip()) >= 2]
    phrase = query.strip()
    if len(phrase) >= 2:
        tokens.append(phrase)
    return sorted(set(tokens), key=len, reverse=True)


def _excerpt_text(text: str, query: str, max_length: int = 280) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_length:
        return collapsed

    match = None
    for term in _query_terms(query):
        found = re.search(re.escape(term), collapsed, re.IGNORECASE)
        if found:
            match = found
            break

    if match is None:
        snippet = collapsed[:max_length].rstrip()
        return f"{snippet}..." if len(collapsed) > len(snippet) else snippet

    half_window = max_length // 2
    start = max(match.start() - half_window, 0)
    end = min(start + max_length, len(collapsed))
    start = max(end - max_length, 0)
    snippet = collapsed[start:end].strip()

    if start > 0:
        snippet = f"...{snippet}"
    if end < len(collapsed):
        snippet = f"{snippet}..."
    return snippet


def _resolve_indexed_source(source: str) -> Path:
    if not source.strip():
        raise HTTPException(status_code=400, detail="Missing source path")

    try:
        candidate = Path(source).expanduser().resolve(strict=True)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc

    chunks_path = Path(os.getenv("CHUNKS_FILE", "data/processed/chunks.jsonl"))
    if not chunks_path.exists():
        raise HTTPException(status_code=404, detail="Document index metadata not found")

    with chunks_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            record = json.loads(line)
            indexed_source = record.get("source")
            if not indexed_source:
                continue
            indexed_path = Path(indexed_source).expanduser().resolve(strict=False)
            if indexed_path == candidate:
                return candidate

    raise HTTPException(status_code=404, detail="Document not found")


if __name__ == "__main__":
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
