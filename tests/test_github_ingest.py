"""Tests for the GitHub issues/PRs ingest tool (issue #217).

All network calls are mocked — no internet required.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Load module
# ---------------------------------------------------------------------------

_MODULE_PATH = (
    Path(__file__).parent.parent / "tools" / "github-ingest" / "ingest.py"
)


@pytest.fixture(scope="module")
def gi():
    spec = importlib.util.spec_from_file_location("github_ingest", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["github_ingest"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# State management
# ---------------------------------------------------------------------------

def test_load_state_empty_when_no_file(gi, tmp_path):
    state = gi.load_state(tmp_path / "state.json")
    assert state == {}


def test_save_and_load_state_roundtrip(gi, tmp_path):
    path = tmp_path / "state.json"
    gi.save_state({"owner/repo": {"issues": {"last_ingest_ts": "2026-03-01T00:00:00Z"}}}, path)
    loaded = gi.load_state(path)
    assert loaded["owner/repo"]["issues"]["last_ingest_ts"] == "2026-03-01T00:00:00Z"


def test_get_last_ingest_ts_none_when_missing(gi):
    assert gi.get_last_ingest_ts("owner/repo", "issues", {}) is None


def test_get_last_ingest_ts_parses_iso_string(gi):
    state = {"owner/repo": {"issues": {"last_ingest_ts": "2026-03-15T12:00:00Z"}}}
    ts = gi.get_last_ingest_ts("owner/repo", "issues", state)
    assert ts is not None
    assert ts.year == 2026 and ts.month == 3 and ts.day == 15


def test_update_last_ingest_ts(gi):
    state = {}
    ts = datetime(2026, 3, 19, 10, 0, 0, tzinfo=timezone.utc)
    updated = gi.update_last_ingest_ts("owner/repo", "prs", state, ts)
    assert updated["owner/repo"]["prs"]["last_ingest_ts"] == "2026-03-19T10:00:00Z"


def test_update_last_ingest_ts_preserves_other_types(gi):
    state = {"owner/repo": {"issues": {"last_ingest_ts": "2026-01-01T00:00:00Z"}}}
    ts = datetime(2026, 3, 19, tzinfo=timezone.utc)
    updated = gi.update_last_ingest_ts("owner/repo", "prs", state, ts)
    assert updated["owner/repo"]["issues"]["last_ingest_ts"] == "2026-01-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Link header parser
# ---------------------------------------------------------------------------

def test_parse_next_link_extracts_next_url(gi):
    header = '<https://api.github.com/repos/foo/bar/issues?page=2>; rel="next", <https://api.github.com/repos/foo/bar/issues?page=5>; rel="last"'
    url = gi._parse_next_link(header)
    assert url == "https://api.github.com/repos/foo/bar/issues?page=2"


def test_parse_next_link_returns_none_when_no_next(gi):
    header = '<https://api.github.com/repos/foo/bar/issues?page=1>; rel="prev"'
    assert gi._parse_next_link(header) is None


def test_parse_next_link_returns_none_for_empty(gi):
    assert gi._parse_next_link(None) is None
    assert gi._parse_next_link("") is None


# ---------------------------------------------------------------------------
# Fake issue/PR data
# ---------------------------------------------------------------------------

_FAKE_ISSUES = json.dumps([
    {
        "number": 42,
        "title": "feat: add semantic search to notes",
        "body": "We need semantic search across all notes in the corpus.",
        "state": "open",
        "labels": [{"name": "enhancement"}, {"name": "ingest"}],
        "created_at": "2026-03-10T09:00:00Z",
        "updated_at": "2026-03-15T12:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/42",
    },
    {
        "number": 43,
        "title": "bug: context store truncates long entries",
        "body": "When a context store entry exceeds 4096 chars it gets silently truncated.",
        "state": "closed",
        "labels": [{"name": "bug"}],
        "created_at": "2026-03-11T10:00:00Z",
        "updated_at": "2026-03-16T08:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/43",
    },
]).encode()

_FAKE_ISSUES_WITH_PR = json.dumps([
    {
        "number": 44,
        "title": "fix: handle empty body in issue normalizer",
        "body": "PR body here.",
        "state": "open",
        "labels": [],
        "created_at": "2026-03-12T00:00:00Z",
        "updated_at": "2026-03-17T00:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/44",
        "pull_request": {"url": "..."},  # this is a PR, should be skipped
    },
    {
        "number": 45,
        "title": "docs: update CLAUDE.md",
        "body": "Update docs.",
        "state": "open",
        "labels": [],
        "created_at": "2026-03-13T00:00:00Z",
        "updated_at": "2026-03-18T00:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/45",
    },
]).encode()

_FAKE_PRS = json.dumps([
    {
        "number": 101,
        "title": "feat: add queue stats endpoint",
        "body": "Adds GET /queue/stats to the MCP server.",
        "state": "merged",
        "labels": [{"name": "feature"}],
        "created_at": "2026-03-14T00:00:00Z",
        "updated_at": "2026-03-18T10:00:00Z",
        "html_url": "https://github.com/owner/repo/pull/101",
    },
]).encode()


def _no_next(raw: bytes) -> tuple[bytes, dict]:
    return raw, {}


# ---------------------------------------------------------------------------
# fetch_issues
# ---------------------------------------------------------------------------

def test_fetch_issues_count(gi):
    issues = list(gi.fetch_issues("owner/repo", fetch_fn=lambda u, t: _no_next(_FAKE_ISSUES)))
    assert len(issues) == 2


def test_fetch_issues_fields(gi):
    issues = list(gi.fetch_issues("owner/repo", fetch_fn=lambda u, t: _no_next(_FAKE_ISSUES)))
    i = issues[0]
    assert i["number"] == 42
    assert i["title"] == "feat: add semantic search to notes"
    assert "enhancement" in i["labels"]
    assert i["item_type"] == "issue"
    assert i["id"] == "github:owner/repo/issues/42"


def test_fetch_issues_skips_prs(gi):
    issues = list(gi.fetch_issues("owner/repo", fetch_fn=lambda u, t: _no_next(_FAKE_ISSUES_WITH_PR)))
    # Should only get the non-PR item (number 45), not number 44 (which has pull_request key)
    assert len(issues) == 1
    assert issues[0]["number"] == 45


def test_fetch_issues_sends_correct_url(gi):
    captured = []

    def fake_fetch(url, token):
        captured.append(url)
        return _no_next(_FAKE_ISSUES)

    list(gi.fetch_issues("owner/repo", fetch_fn=fake_fetch))
    assert len(captured) == 1
    assert "api.github.com" in captured[0]
    assert "owner/repo/issues" in captured[0]


def test_fetch_issues_includes_since_param(gi):
    captured = []

    def fake_fetch(url, token):
        captured.append(url)
        return _no_next(_FAKE_ISSUES)

    since = datetime(2026, 3, 1, tzinfo=timezone.utc)
    list(gi.fetch_issues("owner/repo", since=since, fetch_fn=fake_fetch))
    assert "since=2026-03-01" in captured[0]


def test_fetch_issues_follows_pagination(gi):
    page1 = json.dumps([{
        "number": 1, "title": "T1", "body": "B1", "state": "open",
        "labels": [], "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "html_url": "https://github.com/foo/bar/issues/1",
    }]).encode()
    page2 = json.dumps([{
        "number": 2, "title": "T2", "body": "B2", "state": "open",
        "labels": [], "created_at": "2026-01-02T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
        "html_url": "https://github.com/foo/bar/issues/2",
    }]).encode()

    pages = [page1, page2]
    idx = [0]

    def fake_fetch(url, token):
        raw = pages[idx[0]]
        headers = {"Link": '<http://fake/page2>; rel="next"'} if idx[0] == 0 else {}
        idx[0] += 1
        return raw, headers

    issues = list(gi.fetch_issues("foo/bar", fetch_fn=fake_fetch))
    assert len(issues) == 2


# ---------------------------------------------------------------------------
# fetch_prs
# ---------------------------------------------------------------------------

def test_fetch_prs_count(gi):
    prs = list(gi.fetch_prs("owner/repo", fetch_fn=lambda u, t: _no_next(_FAKE_PRS)))
    assert len(prs) == 1


def test_fetch_prs_fields(gi):
    prs = list(gi.fetch_prs("owner/repo", fetch_fn=lambda u, t: _no_next(_FAKE_PRS)))
    pr = prs[0]
    assert pr["number"] == 101
    assert pr["item_type"] == "pr"
    assert pr["id"] == "github:owner/repo/pulls/101"


def test_fetch_prs_url_contains_pulls(gi):
    captured = []

    def fake_fetch(url, token):
        captured.append(url)
        return _no_next(_FAKE_PRS)

    list(gi.fetch_prs("owner/repo", fetch_fn=fake_fetch))
    assert "owner/repo/pulls" in captured[0]


# ---------------------------------------------------------------------------
# item_to_chunk
# ---------------------------------------------------------------------------

def test_item_to_chunk_contains_title_and_body(gi):
    item = {
        "id": "github:owner/repo/issues/42",
        "number": 42,
        "title": "feat: semantic search",
        "body": "We need this.",
        "state": "open",
        "labels": ["enhancement"],
        "updated_at": "2026-03-15T12:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/42",
        "item_type": "issue",
        "repo": "owner/repo",
    }
    chunk = gi.item_to_chunk(item)
    assert "#42: feat: semantic search" in chunk["chunk"]
    assert "We need this." in chunk["chunk"]
    assert "Labels: enhancement" in chunk["chunk"]
    assert chunk["source"] == "github_issues"
    assert chunk["id"] == "github:owner/repo/issues/42"


def test_item_to_chunk_pr_source(gi):
    item = {
        "id": "github:owner/repo/pulls/101",
        "number": 101,
        "title": "feat: queue stats",
        "body": "Adds stats endpoint.",
        "state": "merged",
        "labels": [],
        "updated_at": "2026-03-18T10:00:00Z",
        "html_url": "https://github.com/owner/repo/pull/101",
        "item_type": "pr",
        "repo": "owner/repo",
    }
    chunk = gi.item_to_chunk(item)
    assert chunk["source"] == "github_prs"


def test_item_to_chunk_empty_body(gi):
    item = {
        "id": "github:owner/repo/issues/5",
        "number": 5,
        "title": "Empty issue",
        "body": "",
        "state": "open",
        "labels": [],
        "updated_at": "2026-03-01T00:00:00Z",
        "html_url": "https://github.com/owner/repo/issues/5",
        "item_type": "issue",
        "repo": "owner/repo",
    }
    chunk = gi.item_to_chunk(item)
    assert chunk["chunk"].startswith("#5: Empty issue")


# ---------------------------------------------------------------------------
# run() — full pipeline with mocked network
# ---------------------------------------------------------------------------

def test_run_writes_jsonl(gi, tmp_path):
    out = tmp_path / "issues.jsonl"
    state_path = tmp_path / "state.json"

    count = gi.run(
        "owner/repo", ["issues"], out, state_path=state_path,
        fetch_fn=lambda u, t: _no_next(_FAKE_ISSUES),
    )
    assert count == 2
    assert out.exists()
    lines = out.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        rec = json.loads(line)
        assert "id" in rec and "chunk" in rec


def test_run_updates_state(gi, tmp_path):
    out = tmp_path / "issues.jsonl"
    state_path = tmp_path / "state.json"

    gi.run(
        "owner/repo", ["issues"], out, state_path=state_path,
        fetch_fn=lambda u, t: _no_next(_FAKE_ISSUES),
    )

    state = gi.load_state(state_path)
    assert "owner/repo" in state
    assert "issues" in state["owner/repo"]
    assert "last_ingest_ts" in state["owner/repo"]["issues"]


def test_run_dry_run_does_not_write(gi, tmp_path):
    out = tmp_path / "issues.jsonl"
    state_path = tmp_path / "state.json"

    count = gi.run(
        "owner/repo", ["issues"], out, state_path=state_path,
        fetch_fn=lambda u, t: _no_next(_FAKE_ISSUES),
        dry_run=True,
    )
    assert count == 2
    assert not out.exists(), "dry-run must not write output"
    assert not state_path.exists(), "dry-run must not update state"


def test_run_multiple_types(gi, tmp_path):
    out = tmp_path / "all.jsonl"
    state_path = tmp_path / "state.json"

    def fake_fetch(url, token):
        if "pulls" in url:
            return _no_next(_FAKE_PRS)
        return _no_next(_FAKE_ISSUES)

    count = gi.run(
        "owner/repo", ["issues", "prs"], out, state_path=state_path,
        fetch_fn=fake_fetch,
    )
    assert count == 3  # 2 issues + 1 PR


def test_run_unknown_type_raises(gi, tmp_path):
    with pytest.raises(ValueError, match="Unknown item types"):
        gi.run("owner/repo", ["unknown"], tmp_path / "out.jsonl",
                state_path=tmp_path / "s.json")
