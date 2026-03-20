"""Tests for new ingest extractors — RED before GREEN.

Covers issues #23 (HTML) and #24 (.md, .csv, .json, .jsonl, .docx).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_extract_html_strips_tags(tmp_path):
    f = tmp_path / "sample.html"
    f.write_text("<html><body><h1>Hello</h1><p>World</p></body></html>")
    from alcove.ingest.extractors import extract_html
    result = extract_html(f)
    assert "Hello" in result
    assert "World" in result
    assert "<" not in result


def test_extract_html_htm_extension(tmp_path):
    f = tmp_path / "sample.htm"
    f.write_text("<p>HTM file works too</p>")
    from alcove.ingest.extractors import extract_html
    result = extract_html(f)
    assert "HTM file works too" in result


def test_extract_md_returns_raw_text(tmp_path):
    f = tmp_path / "sample.md"
    f.write_text("# Heading\n\nSome paragraph text.")
    from alcove.ingest.extractors import extract_md
    result = extract_md(f)
    assert "Heading" in result
    assert "Some paragraph text." in result


def test_extract_rst_returns_raw_text(tmp_path):
    f = tmp_path / "sample.rst"
    f.write_text("Section Title\n=============\n\nBody text here.")
    from alcove.ingest.extractors import extract_rst
    result = extract_rst(f)
    assert "Section Title" in result
    assert "Body text here." in result


def test_extract_csv_returns_all_fields(tmp_path):
    f = tmp_path / "sample.csv"
    f.write_text("name,role\nAlice,engineer\nBob,designer\n")
    from alcove.ingest.extractors import extract_csv
    result = extract_csv(f)
    assert "Alice" in result
    assert "engineer" in result
    assert "Bob" in result


def test_extract_json_object(tmp_path):
    f = tmp_path / "sample.json"
    f.write_text(json.dumps({"title": "Alcove", "description": "local retrieval"}))
    from alcove.ingest.extractors import extract_json
    result = extract_json(f)
    assert "Alcove" in result
    assert "local retrieval" in result


def test_extract_jsonl_multiple_records(tmp_path):
    f = tmp_path / "sample.jsonl"
    lines = [json.dumps({"text": f"record {i}"}) for i in range(3)]
    f.write_text("\n".join(lines))
    from alcove.ingest.extractors import extract_jsonl
    result = extract_jsonl(f)
    assert "record 0" in result
    assert "record 2" in result


def test_extract_docx_returns_paragraph_text(tmp_path):
    docx = pytest.importorskip("docx", reason="python-docx not installed")
    from alcove.ingest.extractors import extract_docx
    doc = docx.Document()
    doc.add_paragraph("Alcove document extraction test.")
    f = tmp_path / "sample.docx"
    doc.save(str(f))
    result = extract_docx(f)
    assert "Alcove document extraction test." in result


def test_pipeline_dispatch_includes_html(tmp_path):
    """Pipeline routes .html files through the extractor without error."""
    import json
    from alcove.ingest.pipeline import run
    f = tmp_path / "doc.html"
    f.write_text("<p>Semantic search content</p>")
    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))
    assert n >= 1
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert any("Semantic search content" in r["chunk"] for r in records)


def test_pipeline_dispatch_includes_md(tmp_path):
    """Pipeline routes .md files through the extractor without error."""
    import json
    from alcove.ingest.pipeline import run
    f = tmp_path / "notes.md"
    f.write_text("# Notes\n\nLocal retrieval is fast.")
    out = tmp_path / "chunks.jsonl"
    n = run(raw_dir=str(tmp_path), out_file=str(out))
    assert n >= 1
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert any("Local retrieval is fast." in r["chunk"] for r in records)


def test_extract_tsv_tab_separated(tmp_path):
    """extract_tsv correctly parses tab-delimited files."""
    f = tmp_path / "data.tsv"
    f.write_text("name\tvalue\nalice\t42\nbob\t100\n")
    from alcove.ingest.extractors import extract_tsv
    result = extract_tsv(f)
    assert "alice" in result
    assert "42" in result
    assert "bob" in result


def test_extract_docx_raises_helpful_import_error(tmp_path):
    """extract_docx raises an ImportError with install instructions when python-docx is absent."""
    import sys
    from unittest.mock import patch
    f = tmp_path / "test.docx"
    f.write_bytes(b"fake content")
    # Simulate python-docx not being installed by hiding it from the import system
    with patch.dict(sys.modules, {"docx": None}):
        from alcove.ingest.extractors import extract_docx
        with pytest.raises(ImportError, match="python-docx is required"):
            extract_docx(f)
