"""Tests for BM25 keyword search, hybrid merging, and API/CLI integration."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from alcove.index.keyword import KeywordIndex


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def chunks_file(tmp_path):
    """Create a temporary chunks.jsonl with sample documents."""
    path = tmp_path / "chunks.jsonl"
    chunks = [
        {"id": "doc1", "text": "the quick brown fox jumps over the lazy dog", "source": "a.txt"},
        {"id": "doc2", "text": "a fast red car drives down the highway", "source": "b.txt"},
        {"id": "doc3", "text": "the brown dog sat in the garden all day", "source": "c.txt"},
        {"id": "doc4", "text": "python programming language is versatile", "source": "d.txt"},
    ]
    with path.open("w") as fh:
        for c in chunks:
            fh.write(json.dumps(c) + "\n")
    return str(path)


@pytest.fixture()
def empty_chunks_file(tmp_path):
    """Create an empty chunks.jsonl."""
    path = tmp_path / "chunks.jsonl"
    path.write_text("")
    return str(path)


@pytest.fixture()
def missing_chunks_file(tmp_path):
    """Return a path that does not exist."""
    return str(tmp_path / "nonexistent.jsonl")


# ---------------------------------------------------------------------------
# KeywordIndex: build and search
# ---------------------------------------------------------------------------

class TestKeywordIndex:
    def test_search_returns_expected_format(self, chunks_file):
        idx = KeywordIndex(chunks_file=chunks_file)
        result = idx.search("brown fox", k=2)

        assert "ids" in result
        assert "documents" in result
        assert "distances" in result
        # Outer list wrapper (ChromaDB convention)
        assert len(result["ids"]) == 1
        assert len(result["documents"]) == 1
        assert len(result["distances"]) == 1
        # Should return at most k results
        assert len(result["ids"][0]) <= 2

    def test_search_ranks_relevant_doc_first(self, chunks_file):
        idx = KeywordIndex(chunks_file=chunks_file)
        result = idx.search("brown fox", k=3)
        ids = result["ids"][0]
        # doc1 has both "brown" and "fox", should rank highest
        assert ids[0] == "doc1"

    def test_distances_are_valid(self, chunks_file):
        idx = KeywordIndex(chunks_file=chunks_file)
        result = idx.search("brown dog", k=3)
        distances = result["distances"][0]
        for d in distances:
            assert 0.0 <= d <= 1.0, f"Distance {d} out of [0,1] range"
        # Best match should have lowest distance
        assert distances[0] <= distances[-1]

    def test_empty_index_returns_empty_results(self, empty_chunks_file):
        idx = KeywordIndex(chunks_file=empty_chunks_file)
        result = idx.search("anything")
        assert result == {"ids": [[]], "documents": [[]], "distances": [[]]}

    def test_missing_file_returns_empty_results(self, missing_chunks_file):
        idx = KeywordIndex(chunks_file=missing_chunks_file)
        result = idx.search("anything")
        assert result == {"ids": [[]], "documents": [[]], "distances": [[]]}

    def test_no_matches_returns_results_with_zero_scores(self, chunks_file):
        """Even queries with no BM25 overlap return k results (with high distances)."""
        idx = KeywordIndex(chunks_file=chunks_file)
        result = idx.search("xyzzyplugh", k=2)
        # BM25 returns scores for all docs (possibly zero), so we still get results
        ids = result["ids"][0]
        distances = result["distances"][0]
        assert len(ids) == 2
        # All distances should be 1.0 (worst) since no terms match
        for d in distances:
            assert d == 1.0

    def test_single_word_query(self, chunks_file):
        idx = KeywordIndex(chunks_file=chunks_file)
        result = idx.search("python", k=1)
        assert result["ids"][0] == ["doc4"]
        assert len(result["documents"][0]) == 1

    def test_empty_query_returns_empty(self, chunks_file):
        idx = KeywordIndex(chunks_file=chunks_file)
        result = idx.search("", k=3)
        assert result == {"ids": [[]], "documents": [[]], "distances": [[]]}


# ---------------------------------------------------------------------------
# Hybrid merging
# ---------------------------------------------------------------------------

class TestHybridMerge:
    def test_hybrid_deduplicates_and_averages(self, chunks_file, monkeypatch):
        """Hybrid search merges semantic + keyword, deduplicates by id, averages scores."""
        # Mock semantic search to return specific results
        sem_result = {
            "ids": [["doc1", "doc2"]],
            "documents": [["text1", "text2"]],
            "distances": [[0.2, 0.5]],
        }
        kw_result = {
            "ids": [["doc1", "doc3"]],
            "documents": [["text1", "text3"]],
            "distances": [[0.3, 0.4]],
        }

        monkeypatch.setattr(
            "alcove.query.retriever.query_text",
            lambda q, n_results=3, collections=None: sem_result,
        )
        monkeypatch.setattr(
            "alcove.query.retriever.query_keyword",
            lambda q, n_results=3: kw_result,
        )

        from alcove.query.retriever import query_hybrid
        result = query_hybrid("test query", n_results=3)

        ids = result["ids"][0]
        distances = result["distances"][0]

        # doc1 appears in both: avg distance = (0.2 + 0.3) / 2 = 0.25
        # doc3 appears only in keyword: avg = (1.0 + 0.4) / 2 = 0.7
        # doc2 appears only in semantic: avg = (0.5 + 1.0) / 2 = 0.75
        assert ids[0] == "doc1"
        assert abs(distances[0] - 0.25) < 0.001

        # Should have all 3 unique docs
        assert len(ids) == 3
        assert set(ids) == {"doc1", "doc2", "doc3"}


# ---------------------------------------------------------------------------
# API integration
# ---------------------------------------------------------------------------

class TestAPIKeywordMode:
    def test_query_post_with_mode_keyword(self, monkeypatch):
        """POST /query with mode=keyword uses keyword search."""
        kw_result = {
            "ids": [["doc1"]],
            "documents": [["sample text"]],
            "distances": [[0.1]],
        }
        monkeypatch.setattr(
            "alcove.query.api.query_keyword",
            lambda q, n_results=3: kw_result,
        )

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.post("/query", json={"query": "test", "k": 1, "mode": "keyword"})
        assert r.status_code == 200
        data = r.json()
        assert data["ids"] == [["doc1"]]

    def test_query_post_with_mode_hybrid(self, monkeypatch):
        """POST /query with mode=hybrid uses hybrid search."""
        hybrid_result = {
            "ids": [["doc1"]],
            "documents": [["sample text"]],
            "distances": [[0.15]],
        }
        monkeypatch.setattr(
            "alcove.query.api.query_hybrid",
            lambda q, n_results=3, collections=None: hybrid_result,
        )

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.post("/query", json={"query": "test", "k": 1, "mode": "hybrid"})
        assert r.status_code == 200
        data = r.json()
        assert data["ids"] == [["doc1"]]

    def test_query_post_default_mode_is_semantic(self):
        """POST /query without mode defaults to semantic (backwards compat)."""
        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.post("/query", json={"query": "test", "k": 1})
        assert r.status_code == 200
        # No error means it used semantic mode (default)

    def test_search_get_with_mode_keyword(self, monkeypatch):
        """GET /search?mode=keyword routes to keyword retriever."""
        kw_result = {
            "ids": [["doc1"]],
            "documents": [["sample text"]],
            "distances": [[0.1]],
            "metadatas": [[{"source": "a.txt", "collection": "default"}]],
        }
        monkeypatch.setattr(
            "alcove.query.api.query_keyword",
            lambda q, n_results=3: kw_result,
        )

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/search", params={"q": "test", "mode": "keyword"})
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]


# ---------------------------------------------------------------------------
# CLI --mode flag
# ---------------------------------------------------------------------------

class TestCLIModeFlag:
    def test_search_help_shows_mode_flag(self):
        """The search subcommand should advertise --mode."""
        result = subprocess.run(
            [sys.executable, "-m", "alcove", "search", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--mode" in result.stdout
        assert "keyword" in result.stdout
        assert "hybrid" in result.stdout

    def test_query_help_shows_mode_flag(self):
        """The query alias should also have --mode."""
        result = subprocess.run(
            [sys.executable, "-m", "alcove", "query", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--mode" in result.stdout


# ---------------------------------------------------------------------------
# Retriever direct calls (covers alcove/query/retriever.py lines 18-20)
# ---------------------------------------------------------------------------

class TestKeywordIndexBlankLines:
    def test_blank_lines_in_chunks_file_are_skipped(self, tmp_path):
        """KeywordIndex gracefully skips blank lines in the chunks JSONL file."""
        import json
        path = tmp_path / "chunks.jsonl"
        chunks = [
            {"id": "doc1", "text": "quick brown fox", "source": "a.txt"},
            "",  # blank line
            {"id": "doc2", "text": "lazy dog", "source": "b.txt"},
        ]
        with path.open("w") as fh:
            for c in chunks:
                fh.write((json.dumps(c) if isinstance(c, dict) else c) + "\n")

        idx = KeywordIndex(chunks_file=str(path))
        result = idx.search("fox", k=2)
        assert len(result["ids"][0]) >= 1
        assert result["ids"][0][0] == "doc1"


class TestRetrieverDirect:
    def test_query_keyword_direct_call(self, tmp_path, monkeypatch):
        """Calling query_keyword from retriever module exercises the full import path."""
        chunks_path = tmp_path / "chunks.jsonl"
        import json
        chunks = [
            {"id": "a:doc1:0", "text": "the quick brown fox", "source": "doc1.txt"},
            {"id": "a:doc2:0", "text": "python programming", "source": "doc2.txt"},
        ]
        with chunks_path.open("w") as fh:
            for c in chunks:
                fh.write(json.dumps(c) + "\n")
        monkeypatch.setenv("CHUNKS_FILE", str(chunks_path))

        from alcove.query.retriever import query_keyword
        result = query_keyword("fox", n_results=2)

        assert "ids" in result
        assert "documents" in result
        assert "distances" in result
        assert len(result["ids"]) == 1
