"""In-process CLI tests for coverage of alcove.cli and alcove.query.cli.

The existing test_cli.py runs subprocess calls which don't register in
coverage. These tests invoke the CLI functions directly with mocked
backends to get full line coverage.
"""
from __future__ import annotations

import argparse
import json
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest


# -----------------------------------------------------------------------
# alcove.cli (main CLI)
# -----------------------------------------------------------------------

class TestFormatSearchResults:
    """Tests for _format_search_results in alcove.cli."""

    def test_formats_results(self, capsys):
        from alcove.cli import _format_search_results
        result = {
            "ids": [["doc1.txt:0", "doc2.txt:0"]],
            "documents": [["The cat sat on the mat.", "Dogs are great."]],
            "distances": [[0.2, 0.5]],
        }
        _format_search_results(result)
        out = capsys.readouterr().out
        assert "0.800" in out  # 1.0 - 0.2
        assert "doc1.txt:0" in out
        assert "cat sat" in out

    def test_no_results(self, capsys):
        from alcove.cli import _format_search_results
        _format_search_results({"ids": [[]], "documents": [[]], "distances": [[]]})
        out = capsys.readouterr().out
        assert "No results found" in out

    def test_long_excerpt_truncated(self, capsys):
        from alcove.cli import _format_search_results
        long_doc = "x" * 300
        result = {
            "ids": [["d1"]],
            "documents": [[long_doc]],
            "distances": [[0.1]],
        }
        _format_search_results(result)
        out = capsys.readouterr().out
        assert "..." in out

    def test_none_distance(self, capsys):
        from alcove.cli import _format_search_results
        result = {
            "ids": [["d1"]],
            "documents": [["text"]],
            "distances": [[None]],
        }
        _format_search_results(result)
        out = capsys.readouterr().out
        assert "0.000" in out


class TestDispatchSearch:
    """Tests for _dispatch_search mode routing.

    _dispatch_search does a lazy import from alcove.query.retriever inside
    the function body, so we patch at the retriever module level.
    """

    def test_default_semantic(self):
        from alcove.cli import _dispatch_search
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("alcove.query.retriever.query_text", return_value=mock_result) as m:
            _dispatch_search("test query", mode="semantic")
        m.assert_called_once_with("test query", n_results=3)

    def test_keyword_mode(self):
        from alcove.cli import _dispatch_search
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("alcove.query.retriever.query_keyword", return_value=mock_result) as m:
            _dispatch_search("test", mode="keyword")
        m.assert_called_once_with("test", n_results=3)

    def test_hybrid_mode(self):
        from alcove.cli import _dispatch_search
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("alcove.query.retriever.query_hybrid", return_value=mock_result) as m:
            _dispatch_search("test", mode="hybrid")
        m.assert_called_once_with("test", n_results=3)


class TestCmdSearch:
    """Tests for cmd_search."""

    def test_json_output(self, capsys):
        from alcove.cli import cmd_search
        mock_result = {"ids": [["d1"]], "documents": [["hello"]], "distances": [[0.1]]}
        args = argparse.Namespace(query="test", k=3, json=True, mode="semantic")
        with patch("alcove.cli._dispatch_search", return_value=mock_result):
            cmd_search(args)
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["ids"] == [["d1"]]

    def test_formatted_output(self, capsys):
        from alcove.cli import cmd_search
        mock_result = {"ids": [["d1"]], "documents": [["hello"]], "distances": [[0.1]]}
        args = argparse.Namespace(query="test", k=3, json=False, mode="semantic")
        with patch("alcove.cli._dispatch_search", return_value=mock_result):
            cmd_search(args)
        out = capsys.readouterr().out
        assert "0.900" in out


class TestCmdStatus:
    """Tests for cmd_status."""

    def test_status_output(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        from alcove.cli import cmd_status
        cmd_status(argparse.Namespace())
        out = capsys.readouterr().out
        assert "index path:" in out
        assert "backend:" in out
        assert "embedder:" in out
        assert "vectors:" in out

    def test_status_unavailable_backend(self, capsys, monkeypatch):
        monkeypatch.setenv("VECTOR_BACKEND", "nonexistent")
        from alcove.cli import cmd_status
        cmd_status(argparse.Namespace())
        out = capsys.readouterr().out
        assert "unavailable" in out


class TestCmdPlugins:
    """Tests for cmd_plugins."""

    def test_no_plugins(self, capsys):
        from alcove.cli import cmd_plugins
        with patch("alcove.plugins.list_plugins", return_value=[]):
            cmd_plugins(argparse.Namespace())
        out = capsys.readouterr().out
        assert "No plugins installed" in out

    def test_with_plugins(self, capsys):
        from alcove.cli import cmd_plugins
        fake = [{"type": "extractor", "name": "test-ext", "module": "test.mod"}]
        with patch("alcove.plugins.list_plugins", return_value=fake):
            cmd_plugins(argparse.Namespace())
        out = capsys.readouterr().out
        assert "test-ext" in out


class TestCmdIngest:
    """Tests for cmd_ingest."""

    def test_ingest_calls_pipeline(self, capsys):
        from alcove.cli import cmd_ingest
        args = argparse.Namespace(path="data/raw", chunk_size=None)
        with patch("alcove.ingest.pipeline.run", return_value=5) as mock_run:
            cmd_ingest(args)
        mock_run.assert_called_once_with(raw_dir="data/raw")
        assert "wrote 5 chunks" in capsys.readouterr().out

    def test_ingest_with_chunk_size(self, monkeypatch):
        from alcove.cli import cmd_ingest
        args = argparse.Namespace(path="data/raw", chunk_size=500)
        with patch("alcove.ingest.pipeline.run", return_value=3):
            cmd_ingest(args)
        assert os.environ.get("CHUNK_SIZE") == "500"


class TestMainEntrypoint:
    """Tests for the main() function and argument parsing."""

    def test_no_command_exits(self):
        from alcove.cli import main
        with patch("sys.argv", ["alcove"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_search_command(self, capsys):
        from alcove.cli import main
        mock_result = {"ids": [["d1"]], "documents": [["hi"]], "distances": [[0.1]]}
        with patch("sys.argv", ["alcove", "search", "hello"]):
            with patch("alcove.cli._dispatch_search", return_value=mock_result):
                main()
        out = capsys.readouterr().out
        assert "0.900" in out

    def test_query_alias(self, capsys):
        from alcove.cli import main
        mock_result = {"ids": [["d1"]], "documents": [["hi"]], "distances": [[0.1]]}
        with patch("sys.argv", ["alcove", "query", "hello"]):
            with patch("alcove.cli._dispatch_search", return_value=mock_result):
                main()
        out = capsys.readouterr().out
        assert "0.900" in out

    def test_search_json_flag(self, capsys):
        from alcove.cli import main
        mock_result = {"ids": [["d1"]], "documents": [["hi"]], "distances": [[0.1]]}
        with patch("sys.argv", ["alcove", "search", "--json", "hello"]):
            with patch("alcove.cli._dispatch_search", return_value=mock_result):
                main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "ids" in parsed

    def test_search_mode_keyword(self, capsys):
        from alcove.cli import main
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("sys.argv", ["alcove", "search", "--mode", "keyword", "hello"]):
            with patch("alcove.cli._dispatch_search", return_value=mock_result) as m:
                main()
        m.assert_called_once_with("hello", k=3, mode="keyword")


# -----------------------------------------------------------------------
# alcove.query.cli (query sub-CLI)
# -----------------------------------------------------------------------

class TestQueryCli:
    """Tests for alcove.query.cli.main."""

    def test_search_subcommand(self, capsys):
        from alcove.query.cli import main
        mock_result = {"ids": [["d1"]], "documents": [["text"]], "distances": [[0.2]]}
        with patch("sys.argv", ["alcove-query", "search", "hello"]):
            with patch("alcove.query.cli.query_text", return_value=mock_result):
                main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["ids"] == [["d1"]]

    def test_search_with_mode_keyword(self, capsys):
        from alcove.query.cli import main
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("sys.argv", ["alcove-query", "search", "--mode", "keyword", "hello"]):
            with patch("alcove.query.cli.query_keyword", return_value=mock_result):
                main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "ids" in parsed

    def test_search_with_mode_hybrid(self, capsys):
        from alcove.query.cli import main
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("sys.argv", ["alcove-query", "search", "--mode", "hybrid", "hello"]):
            with patch("alcove.query.cli.query_hybrid", return_value=mock_result):
                main()
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "ids" in parsed

    def test_search_with_collection_flag(self, capsys):
        from alcove.query.cli import main
        mock_result = {"ids": [[]], "documents": [[]], "distances": [[]]}
        with patch("sys.argv", ["alcove-query", "search", "--collection", "poems", "hello"]):
            with patch("alcove.query.cli.query_text", return_value=mock_result) as m:
                main()
        m.assert_called_once_with("hello", n_results=3, collections=["poems"])

    def test_collections_subcommand_empty(self, capsys, tmp_path, monkeypatch):
        monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))
        from alcove.query.cli import main
        with patch("sys.argv", ["alcove-query", "collections"]):
            main()
        out = capsys.readouterr().out
        assert "No collections found" in out

    def test_collections_subcommand_with_data(self, capsys):
        from alcove.query.cli import main
        fake_colls = [{"name": "poems", "doc_count": 5}]
        mock_backend = MagicMock()
        mock_backend.list_collections.return_value = fake_colls
        with patch("sys.argv", ["alcove-query", "collections"]):
            with patch("alcove.index.backend.get_backend", return_value=mock_backend):
                with patch("alcove.index.embedder.get_embedder"):
                    main()
        out = capsys.readouterr().out
        assert "poems" in out
        assert "5 docs" in out

    def test_legacy_bare_query_exits(self):
        """Bare positional query without subcommand exits with error.

        Note: add_subparsers rejects unknown positional args as invalid
        subcommand choices, so bare queries like ``alcove-query hello``
        are no longer supported. Use ``alcove-query search hello``.
        """
        from alcove.query.cli import main
        with patch("sys.argv", ["alcove-query", "hello"]):
            with pytest.raises(SystemExit):
                main()

    def test_empty_query_errors(self):
        from alcove.query.cli import main
        with patch("sys.argv", ["alcove-query", "search", ""]):
            with pytest.raises(SystemExit):
                main()


import os
