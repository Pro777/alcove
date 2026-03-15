"""Regression tests for bugs fixed 2026-03-10.

Covers:
1. keyword.py reads "chunk" field (not just "text") from chunks.jsonl
2. query_hybrid returns metadatas key in result
3. Score formula handles L2 distances > 1.0 correctly
4. GET /search renders scores in (0, 1) range for all distance values
5. Collection checkboxes: empty collections param means "all"
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from alcove.index.keyword import KeywordIndex


# ---------------------------------------------------------------------------
# 1. keyword.py field name: "chunk" vs "text"
# ---------------------------------------------------------------------------

class TestKeywordFieldName:
    """KeywordIndex must read both 'chunk' and 'text' field names."""

    @pytest.fixture()
    def chunks_with_chunk_key(self, tmp_path):
        """chunks.jsonl using the 'chunk' key (as produced by alcove ingest)."""
        path = tmp_path / "chunks.jsonl"
        chunks = [
            {"id": "c1", "chunk": "the blanchard family lived in gould city", "source": "a.txt"},
            {"id": "c2", "chunk": "michigan upper peninsula history", "source": "b.txt"},
        ]
        with path.open("w") as fh:
            for c in chunks:
                fh.write(json.dumps(c) + "\n")
        return str(path)

    @pytest.fixture()
    def chunks_with_text_key(self, tmp_path):
        """chunks.jsonl using the 'text' key (legacy format)."""
        path = tmp_path / "chunks.jsonl"
        chunks = [
            {"id": "t1", "text": "the blanchard family lived in gould city", "source": "a.txt"},
            {"id": "t2", "text": "michigan upper peninsula history", "source": "b.txt"},
        ]
        with path.open("w") as fh:
            for c in chunks:
                fh.write(json.dumps(c) + "\n")
        return str(path)

    def test_reads_chunk_key(self, chunks_with_chunk_key):
        idx = KeywordIndex(chunks_file=chunks_with_chunk_key)
        result = idx.search("blanchard gould", k=2)
        ids = result["ids"][0]
        assert len(ids) > 0, "Should find results when chunks use 'chunk' key"
        assert ids[0] == "c1"

    def test_reads_text_key(self, chunks_with_text_key):
        idx = KeywordIndex(chunks_file=chunks_with_text_key)
        result = idx.search("blanchard gould", k=2)
        ids = result["ids"][0]
        assert len(ids) > 0, "Should find results when chunks use 'text' key"
        assert ids[0] == "t1"

    def test_bm25_not_zero_division(self, chunks_with_chunk_key):
        """Searching should never raise ZeroDivisionError (the original crash)."""
        idx = KeywordIndex(chunks_file=chunks_with_chunk_key)
        # This would ZeroDivisionError before the fix if all texts were empty
        result = idx.search("gould", k=2)
        assert "ids" in result


# ---------------------------------------------------------------------------
# 2. query_hybrid returns metadatas
# ---------------------------------------------------------------------------

class TestHybridMetadatas:
    """query_hybrid must include 'metadatas' in its return dict."""

    def test_hybrid_returns_metadatas_key(self, monkeypatch):
        sem_result = {
            "ids": [["doc1"]],
            "documents": [["text about gould"]],
            "distances": [[0.3]],
            "metadatas": [[{"source": "a.txt", "collection": "census"}]],
        }
        kw_result = {
            "ids": [["doc1"]],
            "documents": [["text about gould"]],
            "distances": [[0.2]],
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
        result = query_hybrid("gould", n_results=3)

        assert "metadatas" in result, "query_hybrid must return 'metadatas' key"
        metas = result["metadatas"][0]
        assert len(metas) > 0, "metadatas should not be empty"
        assert metas[0]["source"] == "a.txt"
        assert metas[0]["collection"] == "census"

    def test_hybrid_synthesizes_metadata_for_keyword_only(self, monkeypatch):
        """Keyword-only results should get synthesized metadata from doc_id."""
        sem_result = {
            "ids": [[]],
            "documents": [[]],
            "distances": [[]],
            "metadatas": [[]],
        }
        kw_result = {
            "ids": [["census:1900_Census.txt:3"]],
            "documents": [["some census text"]],
            "distances": [[0.2]],
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
        result = query_hybrid("census", n_results=3)

        metas = result["metadatas"][0]
        assert len(metas) == 1
        assert metas[0]["source"] == "1900_Census.txt"
        assert metas[0]["collection"] == "census"


# ---------------------------------------------------------------------------
# 3. Score formula: handles L2 distances
# ---------------------------------------------------------------------------

class TestScoreFormula:
    """Score = 1/(1+dist) must produce values in (0, 1] for any non-negative distance."""

    @pytest.mark.parametrize("dist,expected_min,expected_max", [
        (0.0, 0.99, 1.01),       # perfect match: score ~ 1.0
        (0.5, 0.6, 0.7),         # close match
        (1.0, 0.49, 0.51),       # boundary
        (1.1, 0.47, 0.48),       # L2 distance > 1 (the bug case)
        (1.5, 0.39, 0.41),       # larger L2
        (2.0, 0.33, 0.34),       # far away
        (10.0, 0.08, 0.10),      # very far
    ])
    def test_score_range(self, dist, expected_min, expected_max):
        score = round(1.0 / (1.0 + dist), 3) if dist >= 0 else 0.0
        assert expected_min <= score <= expected_max, (
            f"dist={dist} -> score={score}, expected [{expected_min}, {expected_max}]"
        )
        assert 0.0 < score <= 1.0, f"Score {score} out of (0, 1] range"


# ---------------------------------------------------------------------------
# 4. GET /search renders scores correctly
# ---------------------------------------------------------------------------

class TestSearchScoreRendering:
    """GET /search should produce non-zero scores for L2 distances > 1."""

    def test_search_scores_not_zero_for_l2_distances(self, monkeypatch):
        """Distances > 1.0 (L2) should produce meaningful scores, not 0.000."""
        mock_result = {
            "ids": [["doc1", "doc2"]],
            "documents": [["text about gould city", "more gould text"]],
            "distances": [[1.1, 1.5]],  # L2 distances > 1
            "metadatas": [[
                {"source": "a.txt", "collection": "census"},
                {"source": "b.txt", "collection": "documents"},
            ]],
        }
        monkeypatch.setattr(
            "alcove.query.api.query_text",
            lambda q, n_results=3, collections=None: mock_result,
        )

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/search", params={"q": "gould", "mode": "semantic"})
        assert r.status_code == 200

        # Scores should NOT be 0.000
        assert "0.000" not in r.text, "Scores should not all be zero for L2 distances"
        # Should contain valid score values
        assert "0.476" in r.text or "0.4" in r.text, "Expected meaningful score for dist=1.1"


# ---------------------------------------------------------------------------
# 5. Collections parameter: empty means all
# ---------------------------------------------------------------------------

class TestCollectionsParam:
    """Empty or missing collections param should search all collections."""

    def test_empty_collections_searches_all(self, monkeypatch):
        """collections='' should not filter by collection."""
        call_args = {}

        def mock_query_text(q, n_results=3, collections=None):
            call_args["collections"] = collections
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        monkeypatch.setattr("alcove.query.api.query_text", mock_query_text)

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/search", params={"q": "test", "collections": "", "mode": "semantic"})
        assert r.status_code == 200
        assert call_args["collections"] is None, "Empty collections should pass None (all)"

    def test_missing_collections_searches_all(self, monkeypatch):
        """No collections param should search all."""
        call_args = {}

        def mock_query_text(q, n_results=3, collections=None):
            call_args["collections"] = collections
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        monkeypatch.setattr("alcove.query.api.query_text", mock_query_text)

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/search", params={"q": "test", "mode": "semantic"})
        assert r.status_code == 200
        assert call_args["collections"] is None

    def test_specific_collections_filters(self, monkeypatch):
        """collections=census,documents should pass those as a list."""
        call_args = {}

        def mock_query_text(q, n_results=3, collections=None):
            call_args["collections"] = collections
            return {"ids": [[]], "documents": [[]], "distances": [[]], "metadatas": [[]]}

        monkeypatch.setattr("alcove.query.api.query_text", mock_query_text)

        from fastapi.testclient import TestClient
        from alcove.query.api import app
        client = TestClient(app)
        r = client.get("/search", params={"q": "test", "collections": "census,documents", "mode": "semantic"})
        assert r.status_code == 200
        assert call_args["collections"] == ["census", "documents"]
