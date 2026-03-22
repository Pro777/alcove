#!/usr/bin/env python3
"""Incremental GitHub issues/PRs ingest — fetch new or updated items since last run.

Maintains a per-repo/type state file recording the last successful ingest
timestamp. On each run, only items newer than that timestamp are fetched and
written to a JSONL chunks file for ingestion.

Usage
-----
::

    # Ingest issues from a repo:
    python3 tools/github-ingest/ingest.py --repo owner/repo --types issues \\
        --out data/raw/github/repo_issues.jsonl

    # Ingest both issues and PRs:
    python3 tools/github-ingest/ingest.py --repo owner/repo --types issues,prs \\
        --out data/raw/github/repo.jsonl

    # Preview without updating state:
    python3 tools/github-ingest/ingest.py --repo owner/repo --dry-run

After running, pass the JSONL to alcove::

    alcove ingest --source data/raw/github/ --collection github

Authentication
--------------
Set ``GITHUB_TOKEN`` environment variable for higher rate limits (5000 req/h
vs 60 req/h unauthenticated). Public repos work without a token.

State file
----------
``tools/github-ingest/state.json`` stores::

    {
        "owner/repo": {
            "issues": {"last_ingest_ts": "2026-03-19T00:00:00Z"},
            "prs": {"last_ingest_ts": "2026-03-19T00:00:00Z"}
        }
    }

GitHub API notes
----------------
- Endpoint: ``https://api.github.com/repos/{owner}/{repo}/issues``
  (issues endpoint returns both issues and PRs; use ``pull_request`` key to
  distinguish; use ``?type=issues`` to exclude PRs from the issues endpoint)
- Filter: ``?since=ISO8601`` for updated-at filtering
- Pagination via ``Link`` response header (``rel="next"``)
- Rate limit: 60 req/h unauthenticated; 5000 req/h with token
- Fields used: number, title, body, state, labels, created_at, updated_at,
  html_url, pull_request (presence = is a PR)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GITHUB_API = "https://api.github.com"
STATE_PATH = Path(__file__).parent / "state.json"
SUPPORTED_TYPES = {"issues", "prs"}


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def load_state(state_path: Path = STATE_PATH) -> dict:
    if state_path.exists():
        try:
            return json.loads(state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {}


def save_state(state: dict, state_path: Path = STATE_PATH) -> None:
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def get_last_ingest_ts(repo: str, item_type: str, state: dict) -> datetime | None:
    ts_str = state.get(repo, {}).get(item_type, {}).get("last_ingest_ts")
    if ts_str:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
    return None


def update_last_ingest_ts(
    repo: str, item_type: str, state: dict, ts: datetime
) -> dict:
    state.setdefault(repo, {}).setdefault(item_type, {})["last_ingest_ts"] = (
        ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    return state


# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def _make_request(url: str, token: str | None = None) -> urllib.request.Request:
    headers: dict[str, str] = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "alcove-github-ingest/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def _parse_next_link(link_header: str | None) -> str | None:
    """Extract the ``rel="next"`` URL from a GitHub Link header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        url_part, *rel_parts = (p.strip() for p in part.split(";"))
        if any('rel="next"' in r for r in rel_parts):
            return url_part.strip("<>")
    return None


# ---------------------------------------------------------------------------
# Issues fetcher
# ---------------------------------------------------------------------------

def fetch_issues(
    repo: str,
    since: datetime | None = None,
    *,
    token: str | None = None,
    fetch_fn=None,
) -> Iterator[dict]:
    """Yield issue dicts (excluding PRs) fetched from the GitHub API.

    ``fetch_fn`` is injectable for testing:
    signature ``(url: str, token: str | None) -> tuple[bytes, dict]``
    where the second element is response headers.
    """
    if fetch_fn is None:
        def fetch_fn(url: str, tok: str | None) -> tuple[bytes, dict]:
            req = _make_request(url, tok)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read(), dict(resp.headers)

    params: dict[str, str] = {
        "state": "all",
        "sort": "updated",
        "direction": "desc",
        "per_page": "100",
        "filter": "all",
    }
    if since is not None:
        params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    url: str | None = (
        f"{GITHUB_API}/repos/{repo}/issues?{urllib.parse.urlencode(params)}"
    )

    while url:
        raw, headers = fetch_fn(url, token)
        items = json.loads(raw)
        for item in items:
            # The issues endpoint also returns PRs; skip them here
            if "pull_request" in item:
                continue
            yield _normalize_issue(item, repo)
        url = _parse_next_link(headers.get("Link") or headers.get("link"))


def _normalize_issue(item: dict, repo: str) -> dict:
    labels = [lbl.get("name", "") for lbl in (item.get("labels") or [])]
    return {
        "id": f"github:{repo}/issues/{item['number']}",
        "number": item["number"],
        "title": (item.get("title") or "").strip(),
        "body": (item.get("body") or "").strip(),
        "state": item.get("state", ""),
        "labels": labels,
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "html_url": item.get("html_url", ""),
        "item_type": "issue",
        "repo": repo,
    }


# ---------------------------------------------------------------------------
# PRs fetcher
# ---------------------------------------------------------------------------

def fetch_prs(
    repo: str,
    since: datetime | None = None,
    *,
    token: str | None = None,
    fetch_fn=None,
) -> Iterator[dict]:
    """Yield PR dicts fetched from the GitHub pulls endpoint.

    ``fetch_fn`` is injectable for testing.
    """
    if fetch_fn is None:
        def fetch_fn(url: str, tok: str | None) -> tuple[bytes, dict]:
            req = _make_request(url, tok)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read(), dict(resp.headers)

    params: dict[str, str] = {
        "state": "all",
        "sort": "updated",
        "direction": "desc",
        "per_page": "100",
    }

    url: str | None = (
        f"{GITHUB_API}/repos/{repo}/pulls?{urllib.parse.urlencode(params)}"
    )

    cutoff = since

    while url:
        raw, headers = fetch_fn(url, token)
        items = json.loads(raw)
        stop_early = False
        for item in items:
            updated_str = item.get("updated_at", "")
            if cutoff and updated_str:
                updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                if updated <= cutoff:
                    stop_early = True
                    break
            yield _normalize_pr(item, repo)
        if stop_early:
            break
        url = _parse_next_link(headers.get("Link") or headers.get("link"))


def _normalize_pr(item: dict, repo: str) -> dict:
    labels = [lbl.get("name", "") for lbl in (item.get("labels") or [])]
    return {
        "id": f"github:{repo}/pulls/{item['number']}",
        "number": item["number"],
        "title": (item.get("title") or "").strip(),
        "body": (item.get("body") or "").strip(),
        "state": item.get("state", ""),
        "labels": labels,
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "html_url": item.get("html_url", ""),
        "item_type": "pr",
        "repo": repo,
    }


# ---------------------------------------------------------------------------
# JSONL output
# ---------------------------------------------------------------------------

def item_to_chunk(item: dict) -> dict:
    """Convert a GitHub issue/PR dict to an alcove chunk record."""
    header = f"#{item['number']}: {item['title']}"
    body = item.get("body") or ""
    text = f"{header}\n\n{body}".strip()

    labels_str = ", ".join(item["labels"]) if item["labels"] else ""
    if labels_str:
        text = f"{text}\n\nLabels: {labels_str}"

    item_id = re.sub(r"[^\w:/-]", "_", item["id"])
    return {
        "id": item_id,
        "source": f"github_{item['item_type']}s",
        "chunk": text,
        "title": item["title"],
        "state": item["state"],
        "updated_at": item.get("updated_at", ""),
        "html_url": item.get("html_url", ""),
    }


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run(
    repo: str,
    item_types: list[str],
    out_path: Path,
    state_path: Path = STATE_PATH,
    *,
    dry_run: bool = False,
    token: str | None = None,
    fetch_fn=None,
) -> int:
    """Fetch new/updated GitHub items and write them to *out_path* as JSONL.

    Returns the total number of records written.
    """
    unknown = set(item_types) - SUPPORTED_TYPES
    if unknown:
        raise ValueError(f"Unknown item types: {unknown}. Use: {SUPPORTED_TYPES}")

    state = load_state(state_path)
    now = datetime.now(tz=timezone.utc)

    all_items: list[dict] = []

    for item_type in item_types:
        since = get_last_ingest_ts(repo, item_type, state)
        print(f"Fetching {repo} {item_type} since {since or 'beginning'} …")

        if item_type == "issues":
            items = list(fetch_issues(repo, since=since, token=token, fetch_fn=fetch_fn))
        else:
            items = list(fetch_prs(repo, since=since, token=token, fetch_fn=fetch_fn))

        print(f"  {len(items)} {item_type} found")
        all_items.extend(items)

    print(f"  {len(all_items)} total records")

    if dry_run:
        print("  [dry-run] Not writing output or updating state.")
        return len(all_items)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as fh:
        for item in all_items:
            chunk = item_to_chunk(item)
            fh.write(json.dumps(chunk, ensure_ascii=False) + "\n")
            count += 1

    print(f"Wrote {count} records → {out_path}")

    for item_type in item_types:
        state = update_last_ingest_ts(repo, item_type, state, now)
    save_state(state, state_path)
    print(f"State updated: {repo} → {now.strftime('%Y-%m-%dT%H:%M:%SZ')}")

    return count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--repo", required=True,
        help="GitHub repo in owner/name format (e.g. owner/repo)",
    )
    p.add_argument(
        "--types", default="issues",
        help="Comma-separated item types: issues, prs (default: issues)",
    )
    p.add_argument(
        "--out", default=None,
        help="Output JSONL path (default: data/raw/github/<repo_slug>.jsonl)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Fetch and report count but do not write output or update state",
    )
    p.add_argument(
        "--state", default=str(STATE_PATH),
        help=f"State file path (default: {STATE_PATH})",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    item_types = [t.strip() for t in args.types.split(",") if t.strip()]
    token = os.getenv("GITHUB_TOKEN")

    if args.out:
        out = Path(args.out)
    else:
        repo_root = Path(__file__).resolve().parents[2]
        repo_slug = args.repo.replace("/", "_")
        out = repo_root / "data" / "raw" / "github" / f"{repo_slug}.jsonl"

    run(
        args.repo,
        item_types,
        out,
        state_path=Path(args.state),
        dry_run=args.dry_run,
        token=token,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
