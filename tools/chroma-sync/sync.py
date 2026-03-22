#!/usr/bin/env python3
"""ChromaDB collection sync — export from primary and import to replica.

Exports one or more ChromaDB collections to a portable JSON dump file, then
imports the dump into a target ChromaDB instance.  Stored embeddings are
preserved so the target does not need to re-embed.

Usage
-----
::

    # Export collections from primary:
    python3 tools/chroma-sync/sync.py export \\
        --collections arxiv psyarxiv \\
        --src-host localhost --src-port 8003 \\
        --out /tmp/alcove-sync.json

    # Import on replica:
    python3 tools/chroma-sync/sync.py import \\
        --dump /tmp/alcove-sync.json \\
        --dst-path ~/.alcove/chroma

    # Full sync in one step (must be run where both instances are reachable):
    python3 tools/chroma-sync/sync.py sync \\
        --src-host 192.168.1.10 --src-port 8003 \\
        --dst-path ~/.alcove/chroma \\
        --collections arxiv psyarxiv \\
        --dump /tmp/alcove-sync.json

Transfer
--------
The export produces a single JSON file.  Transfer it between machines with
``rsync`` before running the import step::

    rsync /tmp/alcove-sync.json replica-host:/tmp/alcove-sync.json

Or run both steps from a machine that can reach both ChromaDB instances (e.g.
the replica can reach the primary over the network and also has a local ChromaDB).

Dump format
-----------
::

    {
        "alcove_sync_version": 1,
        "exported_at": "2026-03-19T10:00:00Z",
        "collections": {
            "arxiv": {
                "metadata": {...},
                "ids": [...],
                "documents": [...],
                "metadatas": [...],
                "embeddings": [[...], ...]
            },
            ...
        }
    }
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# ChromaDB client factory — injectable for tests
# ---------------------------------------------------------------------------

def _make_http_client(host: str, port: int):
    import chromadb
    return chromadb.HttpClient(host=host, port=port, settings=chromadb.Settings(anonymized_telemetry=False))


def _make_persistent_client(path: str):
    import chromadb
    return chromadb.PersistentClient(path=path, settings=chromadb.Settings(anonymized_telemetry=False))


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

EXPORT_BATCH_SIZE = 500


def export_collections(
    collection_names: list[str],
    *,
    client_fn=None,
    chroma_host: str = "localhost",
    chroma_port: int = 8000,
) -> dict[str, Any]:
    """Export collections from a ChromaDB instance to a serialisable dict.

    ``client_fn`` is injectable for testing — signature:
    ``() -> chromadb.Client``

    Records are fetched in pages of ``EXPORT_BATCH_SIZE`` to avoid loading
    the entire collection into memory at once.
    """
    if client_fn is None:
        def client_fn():
            return _make_http_client(chroma_host, chroma_port)

    client = client_fn()
    result: dict[str, Any] = {}

    for name in collection_names:
        coll = client.get_collection(name)
        total_count = coll.count()

        ids: list[str] = []
        documents: list[Any] = []
        metadatas: list[Any] = []
        embeddings: list[list[float]] = []

        offset = 0
        while offset < total_count:
            page = coll.get(
                limit=EXPORT_BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas", "embeddings"],
            )
            page_ids = page.get("ids") or []
            if not page_ids:
                break
            ids.extend(page_ids)
            documents.extend(page.get("documents") or [None] * len(page_ids))
            metadatas.extend(page.get("metadatas") or [{}] * len(page_ids))
            embeddings.extend(
                list(e) for e in (page.get("embeddings") or [])
            )
            offset += len(page_ids)

        result[name] = {
            "metadata": getattr(coll, "metadata", None) or {},
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "embeddings": embeddings,
        }
        print(f"  Exported {name}: {len(ids)} documents")

    return result


def write_dump(collections: dict[str, Any], out_path: Path) -> None:
    """Write exported collection data to a JSON dump file."""
    dump = {
        "alcove_sync_version": 1,
        "exported_at": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "collections": collections,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(dump, ensure_ascii=False), encoding="utf-8")
    print(f"Dump written → {out_path}")


def read_dump(dump_path: Path) -> dict[str, Any]:
    """Read and validate a sync dump file."""
    data = json.loads(dump_path.read_text(encoding="utf-8"))
    if data.get("alcove_sync_version") != 1:
        raise ValueError(
            f"Unsupported dump version: {data.get('alcove_sync_version')!r}"
        )
    return data


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

IMPORT_BATCH_SIZE = 500


def import_collections(
    dump: dict[str, Any],
    *,
    client_fn=None,
    chroma_path: str | None = None,
    chroma_host: str | None = None,
    chroma_port: int = 8000,
) -> dict[str, int]:
    """Import collections from a dump dict into a ChromaDB instance.

    Returns ``{collection_name: records_upserted}`` mapping.

    ``client_fn`` is injectable for testing.
    """
    if client_fn is None:
        if chroma_path is not None:
            def client_fn():
                return _make_persistent_client(chroma_path)
        else:
            def client_fn():
                return _make_http_client(chroma_host or "localhost", chroma_port)

    client = client_fn()
    counts: dict[str, int] = {}
    collections = dump.get("collections", {})

    for name, cdata in collections.items():
        ids = cdata.get("ids") or []
        if not ids:
            print(f"  Skipping {name}: no records in dump")
            counts[name] = 0
            continue

        # Get-or-create so re-running is idempotent; restore collection metadata
        coll_metadata = cdata.get("metadata") or None
        coll = client.get_or_create_collection(name, metadata=coll_metadata)

        docs = cdata.get("documents") or [None] * len(ids)
        metas = cdata.get("metadatas") or [None] * len(ids)
        embeddings = cdata.get("embeddings") or None

        # Upsert in batches to avoid request size limits
        total = 0
        for start in range(0, len(ids), IMPORT_BATCH_SIZE):
            end = start + IMPORT_BATCH_SIZE
            doc_slice = docs[start:end]
            batch_kwargs: dict[str, Any] = {
                "ids": ids[start:end],
                "metadatas": [m or {} for m in metas[start:end]],
            }
            if any(d is not None for d in doc_slice):
                batch_kwargs["documents"] = doc_slice
            if embeddings:
                batch_kwargs["embeddings"] = embeddings[start:end]
            coll.upsert(**batch_kwargs)
            total += len(ids[start:end])

        print(f"  Imported {name}: {total} documents")
        counts[name] = total

    return counts


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------

def cmd_export(args) -> int:
    print(f"Exporting from {args.src_host}:{args.src_port} …")
    collections = export_collections(
        args.collections,
        chroma_host=args.src_host,
        chroma_port=args.src_port,
    )
    write_dump(collections, Path(args.out))
    return 0


def cmd_import(args) -> int:
    print(f"Importing from {args.dump} …")
    dump = read_dump(Path(args.dump))
    import_collections(
        dump,
        chroma_path=args.dst_path or None,
        chroma_host=args.dst_host or None,
        chroma_port=args.dst_port,
    )
    return 0


def cmd_sync(args) -> int:
    dump_path = Path(args.dump)
    print(f"Syncing {args.collections} from {args.src_host}:{args.src_port} …")
    collections = export_collections(
        args.collections,
        chroma_host=args.src_host,
        chroma_port=args.src_port,
    )
    write_dump(collections, dump_path)
    print(f"Importing into {args.dst_path or f'{args.dst_host}:{args.dst_port}'} …")
    dump = read_dump(dump_path)
    import_collections(
        dump,
        chroma_path=args.dst_path or None,
        chroma_host=args.dst_host or None,
        chroma_port=args.dst_port,
    )
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="command", required=True)

    # -- export --
    ep = sub.add_parser("export", help="Export collections to a JSON dump")
    ep.add_argument("--collections", nargs="+", required=True,
                    help="Collection names to export")
    ep.add_argument("--src-host", default="localhost",
                    help="Source ChromaDB host (default: localhost)")
    ep.add_argument("--src-port", type=int, default=8000,
                    help="Source ChromaDB port (default: 8000)")
    ep.add_argument("--out", required=True,
                    help="Output dump file path")

    # -- import --
    ip = sub.add_parser("import", help="Import collections from a JSON dump")
    ip.add_argument("--dump", required=True, help="Dump file path")
    dst = ip.add_mutually_exclusive_group(required=True)
    dst.add_argument("--dst-path", help="Target ChromaDB persistent path")
    dst.add_argument("--dst-host", help="Target ChromaDB HTTP host")
    ip.add_argument("--dst-port", type=int, default=8000,
                    help="Target ChromaDB HTTP port (default: 8000)")

    # -- sync --
    sp = sub.add_parser("sync", help="Export from source and import to destination")
    sp.add_argument("--collections", nargs="+", required=True,
                    help="Collection names to sync")
    sp.add_argument("--src-host", default="localhost",
                    help="Source ChromaDB host")
    sp.add_argument("--src-port", type=int, default=8000,
                    help="Source ChromaDB port")
    dst2 = sp.add_mutually_exclusive_group(required=True)
    dst2.add_argument("--dst-path", help="Target ChromaDB persistent path")
    dst2.add_argument("--dst-host", help="Target ChromaDB HTTP host")
    sp.add_argument("--dst-port", type=int, default=8000,
                    help="Target ChromaDB port")
    sp.add_argument("--dump", required=True,
                    help="Intermediate dump file path")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    dispatch = {"export": cmd_export, "import": cmd_import, "sync": cmd_sync}
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
