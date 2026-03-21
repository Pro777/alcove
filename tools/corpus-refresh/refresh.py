#!/usr/bin/env python3
"""Incremental ingest runner for arXiv and PsyArXiv collections.

Queries the arXiv and/or PsyArXiv APIs for papers updated since the last
checkpoint, downloads their metadata, and upserts them into a local Alcove
ChromaDB collection. Designed to be run on a schedule (e.g. daily via cron or
launchd) to keep collections fresh without re-processing the entire corpus.

Usage::

    # Refresh arXiv cs.AI papers updated in the last 7 days
    python tools/corpus-refresh/refresh.py arxiv \\
        --query "cat:cs.AI" --days 7 --chroma-path ./data/chroma

    # Refresh all PsyArXiv
    python tools/corpus-refresh/refresh.py psyarxiv \\
        --days 14 --chroma-path ./data/chroma

    # Dry run — show counts without writing (--dry-run is a global flag, before subcommand)
    python tools/corpus-refresh/refresh.py --dry-run arxiv --query "cat:cs.AI"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator
from urllib import error as urllib_error, parse, request


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_json(url: str, *, timeout: int = 30, retries: int = 3) -> dict:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        req = request.Request(url, headers={"User-Agent": "alcove-corpus-refresh/0.1"})
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (urllib_error.URLError, json.JSONDecodeError) as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_exc}") from last_exc


def _fetch_bytes(url: str, *, timeout: int = 30, retries: int = 3) -> bytes:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        req = request.Request(url, headers={"User-Agent": "alcove-corpus-refresh/0.1"})
        try:
            with request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib_error.URLError as exc:
            last_exc = exc
        if attempt < retries:
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_exc}") from last_exc


# ---------------------------------------------------------------------------
# Checkpoint store
# ---------------------------------------------------------------------------


class CheckpointStore:
    """Persists the last successful refresh timestamp per source/collection."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        # Re-read from disk before writing so overlapping runs (e.g. arxiv +
        # psyarxiv launched concurrently) don't stomp on each other's keys.
        on_disk = self._load()
        on_disk[key] = value
        self._data = on_disk
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically via a temp file + rename so a crash mid-write
        # doesn't leave a truncated checkpoint file.
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(on_disk, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)


# ---------------------------------------------------------------------------
# arXiv source
# ---------------------------------------------------------------------------

_ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(slots=True)
class ArxivPaper:
    id: str
    title: str
    abstract: str
    authors: list[str]
    categories: list[str]
    published: str
    updated: str
    pdf_url: str


def _parse_arxiv_feed(xml_bytes: bytes) -> list[ArxivPaper]:
    """Parse arXiv Atom feed XML into ArxivPaper objects."""
    from defusedxml import ElementTree as ET  # type: ignore[import]

    root = ET.fromstring(xml_bytes)
    papers: list[ArxivPaper] = []

    for entry in root.findall(f"{{{_ATOM_NS}}}entry"):
        id_raw = (entry.findtext(f"{{{_ATOM_NS}}}id") or "").strip()
        arxiv_id = id_raw.rsplit("/", 1)[-1] if "/" in id_raw else id_raw
        title = (entry.findtext(f"{{{_ATOM_NS}}}title") or "").strip()
        title = " ".join(title.split())
        abstract_raw = (entry.findtext(f"{{{_ATOM_NS}}}summary") or "").strip()
        abstract = " ".join(abstract_raw.split())
        published = (entry.findtext(f"{{{_ATOM_NS}}}published") or "").strip()
        updated = (entry.findtext(f"{{{_ATOM_NS}}}updated") or "").strip()

        authors = [
            (a.findtext(f"{{{_ATOM_NS}}}name") or "").strip()
            for a in entry.findall(f"{{{_ATOM_NS}}}author")
        ]
        categories = [
            cat.get("term", "")
            for cat in entry.findall(f"{{{_ATOM_NS}}}category")
        ]
        pdf_url = ""
        for link in entry.findall(f"{{{_ATOM_NS}}}link"):
            if link.get("title") == "pdf":
                pdf_url = link.get("href", "")
                break

        if arxiv_id and abstract:
            papers.append(ArxivPaper(
                id=f"arxiv-{arxiv_id}",
                title=title,
                abstract=abstract,
                authors=authors,
                categories=categories,
                published=published,
                updated=updated,
                pdf_url=pdf_url,
            ))
    return papers


def fetch_arxiv_since(
    query: str,
    since: datetime,
    *,
    max_results: int = 500,
    timeout: int = 30,
) -> list[ArxivPaper]:
    """Fetch arXiv papers matching *query* updated since *since*.

    The arXiv API only supports ``submittedDate`` as a server-side date filter;
    there is no filter for the revision/update date.  We therefore widen the
    server query to all papers submitted since *since*, sort by
    ``lastUpdatedDate``, and then apply a client-side filter on the Atom
    ``<updated>`` field so that only papers whose last revision is ≥ *since*
    are returned.  This catches revisions to older papers while excluding
    un-revised old papers from the result set.

    Args:
        query: arXiv search query string (e.g. ``"cat:cs.AI"``).
        since: Only return papers with ``updated >= since`` (timezone.utc).
        max_results: Maximum number of results per request.
        timeout: HTTP timeout in seconds.
    """
    date_str = since.strftime("%Y%m%d%H%M")
    full_query = f"({query}) AND submittedDate:[{date_str} TO 99991231]"
    params = parse.urlencode({
        "search_query": full_query,
        "max_results": str(max_results),
        "sortBy": "lastUpdatedDate",
        "sortOrder": "descending",
    })
    url = f"{_ARXIV_API}?{params}"
    xml_bytes = _fetch_bytes(url, timeout=timeout)
    papers = _parse_arxiv_feed(xml_bytes)
    # Client-side filter: only keep papers whose last revision is >= since.
    since_aware = since if since.tzinfo is not None else since.replace(tzinfo=timezone.utc)
    filtered: list[ArxivPaper] = []
    for p in papers:
        try:
            updated_dt = datetime.fromisoformat(p.updated)
            if updated_dt.tzinfo is None:
                updated_dt = updated_dt.replace(tzinfo=timezone.utc)
            if updated_dt >= since_aware:
                filtered.append(p)
        except (ValueError, AttributeError):
            filtered.append(p)  # keep if we can't parse the date
    return filtered


# ---------------------------------------------------------------------------
# PsyArXiv source
# ---------------------------------------------------------------------------

_OSF_PREPRINTS_API = "https://api.osf.io/v2/preprints/"


def fetch_psyarxiv_since(
    since: datetime,
    *,
    max_results: int = 500,
    timeout: int = 30,
) -> Iterator[dict]:
    """Yield PsyArXiv preprint metadata dicts updated since *since*.

    Args:
        since: Only return preprints modified after this timezone.utc datetime.
        max_results: Total cap on results to fetch.
        timeout: HTTP timeout per request.
    """
    params = parse.urlencode({
        "filter[provider]": "psyarxiv",
        "filter[date_modified][gte]": since.isoformat(timespec="seconds"),
        "page[size]": "100",
        "sort": "-date_modified",
    })
    url = f"{_OSF_PREPRINTS_API}?{params}"
    fetched = 0

    while url and fetched < max_results:
        data = _fetch_json(url, timeout=timeout)
        items = data.get("data", [])
        for item in items:
            if fetched >= max_results:
                return
            attrs = item.get("attributes", {})
            links = item.get("links", {})
            yield {
                "id": f"psyarxiv-{item.get('id', '')}",
                "title": (attrs.get("title") or "").strip(),
                "abstract": (attrs.get("description") or "").strip(),
                "doi": attrs.get("doi") or "",
                "date_published": attrs.get("date_published") or "",
                "date_modified": attrs.get("date_modified") or "",
                "url": links.get("html") or links.get("self") or "",
                "tags": [t.get("text", "") for t in attrs.get("tags", [])],
            }
            fetched += 1
        url = (data.get("links") or {}).get("next")


# ---------------------------------------------------------------------------
# ChromaDB writer
# ---------------------------------------------------------------------------


class ChromaWriter:
    """Thin wrapper around a ChromaDB PersistentClient.

    This tool is intentionally Chroma-specific: it writes directly to a local
    ``PersistentClient`` without going through the alcove backend abstraction
    layer (``alcove.index``).  That keeps it self-contained and usable without
    installing the full alcove package.  If you need zvec or another backend,
    use the alcove CLI instead.
    """

    def __init__(self, path: Path, collection_name: str) -> None:
        import chromadb  # type: ignore[import]

        self.client = chromadb.PersistentClient(path=str(path))
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def upsert_arxiv(self, papers: list[ArxivPaper]) -> int:
        if not papers:
            return 0
        self.collection.upsert(
            ids=[p.id for p in papers],
            documents=[f"{p.title}\n\n{p.abstract}" for p in papers],
            metadatas=[{
                "title": p.title,
                "authors": ", ".join(p.authors),
                "categories": ", ".join(p.categories),
                "published": p.published,
                "updated": p.updated,
                "pdf_url": p.pdf_url,
                "source": "arxiv",
            } for p in papers],
        )
        return len(papers)

    def upsert_psyarxiv(self, records: list[dict]) -> int:
        if not records:
            return 0
        self.collection.upsert(
            ids=[r["id"] for r in records],
            documents=[f"{r['title']}\n\n{r['abstract']}" for r in records],
            metadatas=[{
                "title": r["title"],
                "doi": r.get("doi", ""),
                "date_published": r.get("date_published", ""),
                "date_modified": r.get("date_modified", ""),
                "url": r.get("url", ""),
                "tags": ", ".join(r.get("tags", [])),
                "source": "psyarxiv",
            } for r in records],
        )
        return len(records)


# ---------------------------------------------------------------------------
# Top-level refresh commands
# ---------------------------------------------------------------------------


def refresh_arxiv(
    query: str,
    *,
    chroma_path: Path,
    collection: str,
    days: int,
    dry_run: bool,
    checkpoint: CheckpointStore,
    timeout: int = 30,
    stream=None,
) -> dict[str, int]:
    """Fetch recent arXiv papers and upsert into the collection."""
    import sys
    out = stream or sys.stdout
    ck_key = f"arxiv:{query}:{collection}"
    since_str = checkpoint.get(ck_key)
    if since_str:
        since = datetime.fromisoformat(since_str)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    # Capture the run boundary BEFORE fetching so that records added during the
    # run are included in the next window and never silently dropped.
    run_ts = _iso_now()
    _MAX_RESULTS = 500
    print(f"Fetching arXiv papers since {since.isoformat()} (query: {query!r})", file=out)
    papers = fetch_arxiv_since(query, since, max_results=_MAX_RESULTS, timeout=timeout)
    print(f"Found {len(papers)} papers", file=out)

    # When the fetch is capped at max_results there may be older papers in the
    # window we didn't retrieve.  Advancing to run_ts would silently skip them.
    # Instead, checkpoint to the oldest returned paper so the next run re-fetches
    # from that boundary and eventually captures the remainder.
    capped = len(papers) >= _MAX_RESULTS
    if capped:
        print(
            f"WARNING: fetch hit the {_MAX_RESULTS}-result cap — some records may be deferred "
            f"to the next run. Checkpointing to oldest fetched record.",
            file=out,
        )
        next_ts = papers[-1].updated if papers else run_ts
    else:
        next_ts = run_ts

    written = 0
    if not dry_run:
        if papers:
            writer = ChromaWriter(chroma_path, collection)
            written = writer.upsert_arxiv(papers)
        # Always advance the checkpoint (even on empty fetch).
        checkpoint.set(ck_key, next_ts)

    return {"fetched": len(papers), "written": written, "capped": capped}


def refresh_psyarxiv(
    *,
    chroma_path: Path,
    collection: str,
    days: int,
    dry_run: bool,
    checkpoint: CheckpointStore,
    timeout: int = 30,
    stream=None,
) -> dict[str, int]:
    """Fetch recent PsyArXiv preprints and upsert into the collection."""
    import sys
    out = stream or sys.stdout
    ck_key = f"psyarxiv:{collection}"
    since_str = checkpoint.get(ck_key)
    if since_str:
        since = datetime.fromisoformat(since_str)
    else:
        since = datetime.now(timezone.utc) - timedelta(days=days)

    run_ts = _iso_now()
    _MAX_RESULTS = 500
    print(f"Fetching PsyArXiv preprints since {since.isoformat()}", file=out)
    records = list(fetch_psyarxiv_since(since, max_results=_MAX_RESULTS, timeout=timeout))
    print(f"Found {len(records)} preprints", file=out)

    capped = len(records) >= _MAX_RESULTS
    if capped:
        print(
            f"WARNING: fetch hit the {_MAX_RESULTS}-result cap — some records may be deferred "
            f"to the next run. Checkpointing to oldest fetched record.",
            file=out,
        )
        next_ts = records[-1].get("date_modified") or run_ts if records else run_ts
    else:
        next_ts = run_ts

    written = 0
    if not dry_run:
        if records:
            writer = ChromaWriter(chroma_path, collection)
            written = writer.upsert_psyarxiv(records)
        checkpoint.set(ck_key, next_ts)

    return {"fetched": len(records), "written": written, "capped": capped}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Incrementally refresh arXiv or PsyArXiv collections in ChromaDB.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--chroma-path",
        default=os.environ.get("CORPUS_CHROMA_PATH", "./data/chroma"),
        help="Persistent ChromaDB path (env: CORPUS_CHROMA_PATH)",
    )
    parser.add_argument(
        "--checkpoint-path",
        default=None,
        help="Path to checkpoint JSON file (default: <chroma-path>/../corpus_refresh_checkpoint.json)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch and count only, do not write")
    parser.add_argument("--timeout", type=int, default=30)

    sub = parser.add_subparsers(dest="source", required=True)

    arxiv = sub.add_parser("arxiv", help="Refresh arXiv papers")
    arxiv.add_argument("--query", required=True, help="arXiv search query (e.g. 'cat:cs.AI')")
    arxiv.add_argument("--days", type=int, default=7, help="Fetch papers updated in the last N days")
    arxiv.add_argument(
        "--collection",
        default=os.environ.get("ARXIV_COLLECTION", "arxiv"),
        help="ChromaDB collection name",
    )

    psyarxiv = sub.add_parser("psyarxiv", help="Refresh PsyArXiv preprints")
    psyarxiv.add_argument("--days", type=int, default=7)
    psyarxiv.add_argument(
        "--collection",
        default=os.environ.get("PSYARXIV_COLLECTION", "psyarxiv"),
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    chroma_path = Path(args.chroma_path)
    ck_path = (
        Path(args.checkpoint_path)
        if args.checkpoint_path
        else chroma_path.parent / "corpus_refresh_checkpoint.json"
    )
    checkpoint = CheckpointStore(ck_path)

    if args.source == "arxiv":
        stats = refresh_arxiv(
            args.query,
            chroma_path=chroma_path,
            collection=args.collection,
            days=args.days,
            dry_run=args.dry_run,
            checkpoint=checkpoint,
            timeout=args.timeout,
        )
    elif args.source == "psyarxiv":
        stats = refresh_psyarxiv(
            chroma_path=chroma_path,
            collection=args.collection,
            days=args.days,
            dry_run=args.dry_run,
            checkpoint=checkpoint,
            timeout=args.timeout,
        )
    else:
        raise ValueError(f"Unsupported source: {args.source!r}. Valid sources: arxiv, psyarxiv")

    print(f"Done: {stats}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
