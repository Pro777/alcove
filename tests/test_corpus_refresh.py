"""Tests for tools/corpus-refresh/refresh.py.

Tests cover pure functions and classes that require no network access:
CheckpointStore, _parse_arxiv_feed, fetch_psyarxiv_since (mocked),
ArxivPaper, ChromaWriter (mocked), and CLI argument parsing.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Module loader (no package install required)
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
REFRESH_PY = REPO_ROOT / "tools" / "corpus-refresh" / "refresh.py"


@pytest.fixture(scope="module")
def refresh():
    spec = importlib.util.spec_from_file_location("refresh", REFRESH_PY)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["refresh"] = mod  # Required for @dataclass(slots=True) annotation resolution
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# CheckpointStore
# ---------------------------------------------------------------------------


class TestCheckpointStore:
    def test_get_returns_none_when_missing(self, refresh, tmp_path):
        store = refresh.CheckpointStore(tmp_path / "ck.json")
        assert store.get("arxiv:cat:cs.AI:arxiv") is None

    def test_set_and_get_roundtrip(self, refresh, tmp_path):
        store = refresh.CheckpointStore(tmp_path / "ck.json")
        store.set("key1", "2025-01-01T00:00:00+00:00")
        assert store.get("key1") == "2025-01-01T00:00:00+00:00"

    def test_persists_to_disk(self, refresh, tmp_path):
        path = tmp_path / "ck.json"
        store = refresh.CheckpointStore(path)
        store.set("k", "v")
        # reload from disk
        store2 = refresh.CheckpointStore(path)
        assert store2.get("k") == "v"

    def test_handles_corrupt_file(self, refresh, tmp_path):
        path = tmp_path / "ck.json"
        path.write_text("not json", encoding="utf-8")
        store = refresh.CheckpointStore(path)
        assert store.get("anything") is None

    def test_multiple_keys(self, refresh, tmp_path):
        store = refresh.CheckpointStore(tmp_path / "ck.json")
        store.set("a", "1")
        store.set("b", "2")
        assert store.get("a") == "1"
        assert store.get("b") == "2"

    def test_creates_parent_dirs(self, refresh, tmp_path):
        path = tmp_path / "sub" / "dir" / "ck.json"
        store = refresh.CheckpointStore(path)
        store.set("k", "v")
        assert path.exists()


# ---------------------------------------------------------------------------
# _parse_arxiv_feed
# ---------------------------------------------------------------------------

_MINIMAL_ATOM = b"""\
<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"
      xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v2</id>
    <title>Test Paper Title</title>
    <summary>This is the abstract text.</summary>
    <published>2024-01-15T00:00:00Z</published>
    <updated>2024-01-20T00:00:00Z</updated>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
    <link title="pdf" href="https://arxiv.org/pdf/2401.12345v2"/>
  </entry>
</feed>
"""

_ATOM_NO_ABSTRACT = b"""\
<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.99999v1</id>
    <title>No Abstract Paper</title>
    <summary></summary>
    <published>2024-01-15T00:00:00Z</published>
    <updated>2024-01-15T00:00:00Z</updated>
  </entry>
</feed>
"""


class TestParseArxivFeed:
    def test_parses_single_entry(self, refresh):
        papers = refresh._parse_arxiv_feed(_MINIMAL_ATOM)
        assert len(papers) == 1
        p = papers[0]
        assert p.id == "arxiv-2401.12345v2"
        assert p.title == "Test Paper Title"
        assert p.abstract == "This is the abstract text."

    def test_authors_extracted(self, refresh):
        papers = refresh._parse_arxiv_feed(_MINIMAL_ATOM)
        assert papers[0].authors == ["Alice Smith", "Bob Jones"]

    def test_categories_extracted(self, refresh):
        papers = refresh._parse_arxiv_feed(_MINIMAL_ATOM)
        assert "cs.AI" in papers[0].categories
        assert "cs.LG" in papers[0].categories

    def test_pdf_url_extracted(self, refresh):
        papers = refresh._parse_arxiv_feed(_MINIMAL_ATOM)
        assert papers[0].pdf_url == "https://arxiv.org/pdf/2401.12345v2"

    def test_published_and_updated(self, refresh):
        papers = refresh._parse_arxiv_feed(_MINIMAL_ATOM)
        assert papers[0].published == "2024-01-15T00:00:00Z"
        assert papers[0].updated == "2024-01-20T00:00:00Z"

    def test_skips_entry_without_abstract(self, refresh):
        papers = refresh._parse_arxiv_feed(_ATOM_NO_ABSTRACT)
        assert papers == []

    def test_empty_feed(self, refresh):
        empty = b"""<?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom"></feed>"""
        assert refresh._parse_arxiv_feed(empty) == []

    def test_id_strips_url_prefix(self, refresh):
        papers = refresh._parse_arxiv_feed(_MINIMAL_ATOM)
        assert not papers[0].id.startswith("arxiv-http")


# ---------------------------------------------------------------------------
# fetch_psyarxiv_since (mocked HTTP)
# ---------------------------------------------------------------------------


class TestFetchPsyarxivSince:
    def _make_item(self, id_, title, abstract="Abstract text"):
        return {
            "id": id_,
            "attributes": {
                "title": title,
                "description": abstract,
                "doi": f"10.1234/{id_}",
                "date_published": "2024-01-01T00:00:00Z",
                "date_modified": "2024-01-02T00:00:00Z",
                "tags": [{"text": "psychology"}, {"text": "cognition"}],
            },
            "links": {"html": f"https://osf.io/{id_}"},
        }

    def test_yields_records(self, refresh):
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(days=7)
        page = self._make_page([self._make_item("abc123", "Paper One")])

        with patch.object(refresh, "_fetch_json", return_value=page):
            records = list(refresh.fetch_psyarxiv_since(since, max_results=10))

        assert len(records) == 1
        assert records[0]["id"] == "psyarxiv-abc123"
        assert records[0]["title"] == "Paper One"

    def _make_page(self, items, *, next_url=None):
        return {"data": items, "links": {"next": next_url}}

    def test_respects_max_results(self, refresh):
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(days=7)
        items = [self._make_item(f"id{i}", f"Paper {i}") for i in range(20)]
        page = self._make_page(items)

        with patch.object(refresh, "_fetch_json", return_value=page):
            records = list(refresh.fetch_psyarxiv_since(since, max_results=5))

        assert len(records) == 5

    def test_tags_joined(self, refresh):
        from datetime import datetime, timedelta, timezone

        since = datetime.now(timezone.utc) - timedelta(days=7)
        item = self._make_item("xyz", "Tagged Paper")
        page = self._make_page([item])

        with patch.object(refresh, "_fetch_json", return_value=page):
            records = list(refresh.fetch_psyarxiv_since(since, max_results=10))

        assert records[0]["tags"] == ["psychology", "cognition"]


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLIArgParsing:
    def test_arxiv_subcommand_requires_query(self, refresh):
        parser = refresh._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["arxiv"])

    def test_arxiv_subcommand_parses(self, refresh):
        parser = refresh._build_parser()
        args = parser.parse_args([
            "--chroma-path", "/tmp/chroma",
            "arxiv", "--query", "cat:cs.AI", "--days", "7",
        ])
        assert args.source == "arxiv"
        assert args.query == "cat:cs.AI"
        assert args.days == 7

    def test_psyarxiv_subcommand_parses(self, refresh):
        parser = refresh._build_parser()
        args = parser.parse_args([
            "--chroma-path", "/tmp/chroma",
            "psyarxiv", "--days", "14",
        ])
        assert args.source == "psyarxiv"
        assert args.days == 14

    def test_dry_run_flag(self, refresh):
        parser = refresh._build_parser()
        args = parser.parse_args(["--dry-run", "arxiv", "--query", "cat:cs.AI"])
        assert args.dry_run is True

    def test_default_days(self, refresh):
        parser = refresh._build_parser()
        args = parser.parse_args(["arxiv", "--query", "cat:cs.AI"])
        assert args.days == 7


# ---------------------------------------------------------------------------
# refresh_arxiv / refresh_psyarxiv (dry-run, no ChromaDB needed)
# ---------------------------------------------------------------------------


class TestRefreshArxivDryRun:
    def test_dry_run_returns_fetched_count(self, refresh, tmp_path):
        from datetime import datetime, timedelta, timezone

        papers = [
            refresh.ArxivPaper(
                id=f"arxiv-240{i}.{i:05d}v1",
                title=f"Paper {i}",
                abstract=f"Abstract {i}",
                authors=["Author A"],
                categories=["cs.AI"],
                published="2024-01-01T00:00:00Z",
                updated="2024-01-02T00:00:00Z",
                pdf_url=f"https://arxiv.org/pdf/240{i}.{i:05d}v1",
            )
            for i in range(3)
        ]

        ck = refresh.CheckpointStore(tmp_path / "ck.json")

        with patch.object(refresh, "fetch_arxiv_since", return_value=papers):
            stats = refresh.refresh_arxiv(
                "cat:cs.AI",
                chroma_path=tmp_path / "chroma",
                collection="arxiv",
                days=7,
                dry_run=True,
                checkpoint=ck,
            )

        assert stats["fetched"] == 3
        assert stats["written"] == 0

    def test_dry_run_does_not_update_checkpoint(self, refresh, tmp_path):
        from datetime import datetime, timedelta, timezone

        ck = refresh.CheckpointStore(tmp_path / "ck.json")

        with patch.object(refresh, "fetch_arxiv_since", return_value=[]):
            refresh.refresh_arxiv(
                "cat:cs.AI",
                chroma_path=tmp_path / "chroma",
                collection="arxiv",
                days=7,
                dry_run=True,
                checkpoint=ck,
            )

        assert ck.get("arxiv:cat:cs.AI:arxiv") is None


class TestRefreshPsyarxivDryRun:
    def test_dry_run_returns_fetched_count(self, refresh, tmp_path):
        records = [
            {
                "id": f"psyarxiv-abc{i}",
                "title": f"Preprint {i}",
                "abstract": f"Abstract {i}",
                "doi": "",
                "date_published": "2024-01-01T00:00:00Z",
                "date_modified": "2024-01-02T00:00:00Z",
                "url": f"https://osf.io/abc{i}",
                "tags": [],
            }
            for i in range(5)
        ]

        ck = refresh.CheckpointStore(tmp_path / "ck.json")

        with patch.object(refresh, "fetch_psyarxiv_since", return_value=iter(records)):
            stats = refresh.refresh_psyarxiv(
                chroma_path=tmp_path / "chroma",
                collection="psyarxiv",
                days=7,
                dry_run=True,
                checkpoint=ck,
            )

        assert stats["fetched"] == 5
        assert stats["written"] == 0


class TestCheckpointAdvancesOnEmptyFetch:
    """Checkpoint should advance even when no records are fetched (avoids re-scanning)."""

    def test_arxiv_empty_fetch_still_updates_checkpoint(self, refresh, tmp_path):
        ck = refresh.CheckpointStore(tmp_path / "ck.json")
        with patch.object(refresh, "fetch_arxiv_since", return_value=[]):
            refresh.refresh_arxiv(
                "cat:cs.AI",
                chroma_path=tmp_path / "chroma",
                collection="arxiv",
                days=7,
                dry_run=False,
                checkpoint=ck,
            )
        assert ck.get("arxiv:cat:cs.AI:arxiv") is not None

    def test_psyarxiv_empty_fetch_still_updates_checkpoint(self, refresh, tmp_path):
        ck = refresh.CheckpointStore(tmp_path / "ck.json")
        with patch.object(refresh, "fetch_psyarxiv_since", return_value=iter([])):
            refresh.refresh_psyarxiv(
                chroma_path=tmp_path / "chroma",
                collection="psyarxiv",
                days=7,
                dry_run=False,
                checkpoint=ck,
            )
        assert ck.get("psyarxiv:psyarxiv") is not None
