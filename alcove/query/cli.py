from __future__ import annotations

import argparse
import json

from .retriever import query_hybrid, query_keyword, query_text


def main():
    parser = argparse.ArgumentParser(description="Alcove CLI")
    sub = parser.add_subparsers(dest="command")

    # Search subcommand (also the default when no subcommand given)
    search_parser = sub.add_parser("search", help="Search the index")
    search_parser.add_argument("query", nargs="?", default="", help="question or search phrase")
    search_parser.add_argument("--k", type=int, default=3)
    search_parser.add_argument(
        "--collection", action="append", default=None,
        help="Filter by collection (repeatable)",
    )
    search_parser.add_argument(
        "--mode", choices=["semantic", "keyword", "hybrid"],
        default="semantic", help="Search mode (default: semantic)",
    )

    # Collections subcommand
    sub.add_parser("collections", help="List all collections")

    # Backwards compat: bare positional query without subcommand
    args, remaining = parser.parse_known_args()

    if args.command == "collections":
        _list_collections()
        return

    if args.command == "search":
        query = args.query
        k = args.k
        collections = args.collection
        mode = args.mode
    else:
        # No subcommand: treat all args as a legacy-style search
        legacy = argparse.ArgumentParser()
        legacy.add_argument("query", nargs="?", default="")
        legacy.add_argument("--k", type=int, default=3)
        legacy.add_argument("--collection", action="append", default=None)
        legacy.add_argument(
            "--mode", choices=["semantic", "keyword", "hybrid"],
            default="semantic",
        )
        args = legacy.parse_args()
        query = args.query
        k = args.k
        collections = args.collection
        mode = args.mode

    if not query.strip():
        parser.error('Usage: alcove search "your question here"')

    res = _run_query(query, k=k, mode=mode, collections=collections)
    print(json.dumps(res, indent=2))


def _run_query(query, k=3, mode="semantic", collections=None):
    """Dispatch to the correct retriever based on search mode."""
    if mode == "keyword":
        return query_keyword(query, n_results=k)
    elif mode == "hybrid":
        return query_hybrid(query, n_results=k, collections=collections)
    else:
        return query_text(query, n_results=k, collections=collections)


def _list_collections():
    """Print collections from the backend."""
    from alcove.index.backend import get_backend
    from alcove.index.embedder import get_embedder
    try:
        backend = get_backend(get_embedder())
        colls = backend.list_collections()
    except Exception:
        colls = []
    if not colls:
        print("No collections found.")
        return
    for c in colls:
        print(f"  {c['name']}  ({c['doc_count']} docs)")


if __name__ == "__main__":
    main()
