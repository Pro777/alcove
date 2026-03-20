"""Tests for empty/whitespace-only file skipping during ingest."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _read_chunks(out_file: Path) -> list[dict]:
    if not out_file.exists():
        return []
    records = []
    for line in out_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def test_empty_file_is_skipped(tmp_path):
    """Pipeline should skip files with no extractable text."""
    from alcove.ingest.pipeline import run

    empty = tmp_path / "empty.txt"
    empty.write_text("")

    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))

    assert n == 0, f"Expected 0 chunks, got {n}"
    assert _read_chunks(out) == [], "Expected no chunk records in output"


def test_whitespace_only_file_is_skipped(tmp_path):
    """Pipeline should skip files containing only whitespace."""
    from alcove.ingest.pipeline import run

    ws = tmp_path / "blank.txt"
    ws.write_text("   \n\t\n   ")

    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))

    assert n == 0, f"Expected 0 chunks, got {n}"
    assert _read_chunks(out) == [], "Expected no chunk records in output"


def test_empty_file_logs_warning(tmp_path, caplog):
    """Pipeline should emit a warning when skipping an empty file."""
    import logging
    from alcove.ingest.pipeline import run

    empty = tmp_path / "empty.txt"
    empty.write_text("")

    out = tmp_path / "chunks.jsonl"
    with caplog.at_level(logging.WARNING, logger="alcove.ingest.pipeline"):
        run(raw_dir=str(tmp_path), out_file=str(out))

    assert any("empty" in rec.message.lower() for rec in caplog.records), (
        f"Expected a warning about skipping empty file; got: {[r.message for r in caplog.records]}"
    )


def test_nonempty_file_is_not_skipped(tmp_path):
    """Pipeline should still index files that have real content."""
    from alcove.ingest.pipeline import run

    content = tmp_path / "content.txt"
    content.write_text("This is a real document with actual content worth indexing.")

    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))

    assert n > 0, "Expected at least one chunk for a non-empty file"


def test_index_pipeline_returns_zero_for_empty_chunks(tmp_path, monkeypatch):
    """alcove.index.pipeline.run() returns 0 when the chunks file is empty."""
    from alcove.index.pipeline import run

    chunks_file = tmp_path / "chunks.jsonl"
    chunks_file.write_text("")  # empty file
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "chroma"))

    n = run(chunks_file=str(chunks_file))
    assert n == 0


def test_chunk_text_empty_returns_empty_list():
    """chunk_text on empty/whitespace-only text returns []."""
    from alcove.ingest.pipeline import chunk_text
    assert chunk_text("", size=500, overlap=50) == []
    assert chunk_text("   ", size=500, overlap=50) == []


def test_pipeline_skips_subdirectories(tmp_path):
    """Directories inside raw_dir are skipped (only files are processed)."""
    from alcove.ingest.pipeline import run

    (tmp_path / "subdir").mkdir()
    (tmp_path / "doc.txt").write_text("real content here for indexing purposes")
    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))
    assert n >= 1  # subdir was skipped, doc.txt was processed


def test_pipeline_skips_unsupported_extension(tmp_path):
    """Files with unrecognised extensions are silently skipped."""
    from alcove.ingest.pipeline import run

    (tmp_path / "archive.zip").write_bytes(b"PK\x03\x04fake")
    (tmp_path / "doc.txt").write_text("searchable content here")
    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))
    # zip is skipped, txt is processed
    assert n >= 1
    records = _read_chunks(out)
    assert all("zip" not in r["source"] for r in records)


def test_pipeline_skips_file_that_raises(tmp_path, capsys):
    """Extractor exceptions are caught and the file is skipped with a message."""
    from unittest.mock import patch
    from alcove.ingest.pipeline import run

    bad_file = tmp_path / "corrupt.txt"
    bad_file.write_text("some content")
    good_file = tmp_path / "good.txt"
    good_file.write_text("this file is fine and should be indexed correctly")

    out = tmp_path / "chunks.jsonl"

    def boom(path):
        if path.name == "corrupt.txt":
            raise ValueError("corrupt file simulation")
        return path.read_text()

    with patch("alcove.ingest.pipeline._get_extractors", return_value={".txt": boom}):
        n = run(raw_dir=str(tmp_path), out_file=str(out))

    captured = capsys.readouterr()
    assert "skipped" in captured.out
    assert "corrupt.txt" in captured.out
    assert n >= 1  # good.txt was still indexed
