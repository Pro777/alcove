"""Alcove CLI -- local-first document retrieval."""

from __future__ import annotations

import argparse
import json
import os
import sys

from alcove import __version__


def cmd_serve(args):
    import uvicorn
    if args.root_path:
        os.environ["ALCOVE_ROOT_PATH"] = args.root_path.rstrip("/")
    from alcove.query.api import app
    uvicorn.run(app, host=args.host, port=args.port)


def cmd_ingest(args):
    from alcove.ingest.pipeline import run
    if args.chunk_size is not None:
        os.environ["CHUNK_SIZE"] = str(args.chunk_size)
    n = run(raw_dir=args.path)
    print(f"wrote {n} chunks")


def _format_search_results(result):
    """Print search results in human-readable format."""
    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]

    if not ids:
        print("No results found.")
        return

    for i, (doc_id, doc, dist) in enumerate(zip(ids, documents, distances)):
        if i > 0:
            print()
        score = 1.0 - dist if dist is not None else 0.0
        source = doc_id if doc_id else "(unknown)"
        excerpt = (doc[:200] + "...") if doc and len(doc) > 200 else (doc or "")
        print(f'  score: {score:.3f}  |  {source}')
        print(f'  "{excerpt}"')


def _dispatch_search(query, k=3, mode="semantic"):
    """Route to the correct retriever based on search mode."""
    from alcove.query.retriever import query_hybrid, query_keyword, query_text
    if mode == "keyword":
        return query_keyword(query, n_results=k)
    elif mode == "hybrid":
        return query_hybrid(query, n_results=k)
    else:
        return query_text(query, n_results=k)


def cmd_search(args):
    mode = getattr(args, "mode", "semantic")
    result = _dispatch_search(args.query, k=args.k, mode=mode)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        _format_search_results(result)


def cmd_status(_args):
    from alcove.index.embedder import get_embedder
    from alcove.index.backend import get_backend

    index_path = os.getenv("CHROMA_PATH", "./data/chroma")
    embedder_name = os.getenv("EMBEDDER", "hash")
    backend_name = os.getenv("VECTOR_BACKEND", "chromadb")

    try:
        embedder = get_embedder()
        backend = get_backend(embedder)
        count = backend.count()
        count_str = str(count)
    except Exception as exc:
        count_str = f"(unavailable: {exc})"

    print(f"  index path:     {index_path}")
    print(f"  backend:        {backend_name}")
    print(f"  embedder:       {embedder_name}")
    print(f"  vectors:        {count_str}")
    print(f"  network:        none required")


def cmd_plugins(_args):
    from alcove.plugins import list_plugins
    plugins = list_plugins()
    if not plugins:
        print("No plugins installed.")
        print("Install plugins via pip, e.g.: pip install alcove-docx")
        return
    for p in plugins:
        print(f"  {p['type']:10s}  {p['name']:20s}  {p['module']}")


def cmd_collections(_args):
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


def cmd_seed_demo(_args):
    import subprocess
    from pathlib import Path
    scripts_dir = Path("scripts")
    if not scripts_dir.is_dir():
        print("Error: 'scripts/' directory not found. Run seed-demo from the Alcove repo root.", file=sys.stderr)
        sys.exit(1)
    for s in ["fetch_seed_corpus.py", "ingest_seed_demo.py", "build_seed_index.py"]:
        script_path = scripts_dir / s
        if not script_path.is_file():
            print(f"Error: '{script_path}' not found.", file=sys.stderr)
            sys.exit(1)
        subprocess.check_call([sys.executable, str(script_path)])


def _add_search_parser(sub, name, hidden=False):
    """Add a search/query subparser. Used for both the primary and alias."""
    help_text = argparse.SUPPRESS if hidden else "Search local index"
    p = sub.add_parser(name, help=help_text)
    p.add_argument("query", help="Search terms")
    p.add_argument("--k", type=int, default=3, help="Number of results (default: 3)")
    p.add_argument("--json", action="store_true", default=False, help="Output raw JSON instead of formatted results")
    p.add_argument(
        "--mode", choices=["semantic", "keyword", "hybrid"],
        default="semantic", help="Search mode (default: semantic)",
    )
    p.set_defaults(func=cmd_search)
    return p


def main():
    parser = argparse.ArgumentParser(
        prog="alcove",
        description="Local-first document retrieval. Your data never leaves your disk.",
    )
    parser.add_argument("--version", action="version", version=f"alcove {__version__}")
    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="Start web UI and API server")
    p_serve.add_argument("--host", default="127.0.0.1", help="Bind address (default: 127.0.0.1; use 0.0.0.0 to expose on network)")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument(
        "--root-path", default="",
        help="URL prefix when served behind a reverse proxy (e.g. /demos). "
             "Sets ALCOVE_ROOT_PATH env var.",
    )
    p_serve.set_defaults(func=cmd_serve)

    # ingest
    p_ingest = sub.add_parser("ingest", help="Ingest documents from a directory")
    p_ingest.add_argument("path", nargs="?", default=None, help="Directory with raw documents")
    p_ingest.add_argument("--chunk-size", type=int, default=None, help="Chunk size in characters (default: 1000)")
    p_ingest.set_defaults(func=cmd_ingest)

    # search (primary)
    _add_search_parser(sub, "search")

    # query (hidden alias for backwards compatibility)
    _add_search_parser(sub, "query", hidden=True)

    # collections
    p_colls = sub.add_parser("collections", help="List named collections")
    p_colls.set_defaults(func=cmd_collections)

    # status
    p_status = sub.add_parser("status", help="Show index and configuration status")
    p_status.set_defaults(func=cmd_status)

    # seed-demo
    p_seed = sub.add_parser("seed-demo", help="Fetch and index demo corpus")
    p_seed.set_defaults(func=cmd_seed_demo)

    # plugins
    p_plugins = sub.add_parser("plugins", help="List installed plugins")
    p_plugins.set_defaults(func=cmd_plugins)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)
    args.func(args)
