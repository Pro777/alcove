"""Tests for tools/audit-log/audit_log.py."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "audit-log" / "audit_log.py"


def _load_module() -> ModuleType:
    _mod_key = "audit_log_test_module"
    spec = importlib.util.spec_from_file_location(_mod_key, _MODULE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {_MODULE_PATH}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_mod_key] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        sys.modules.pop(_mod_key, None)
        raise
    return mod


@pytest.fixture(scope="module")
def al() -> ModuleType:
    _mod_key = "audit_log_test_module"
    prev = sys.modules.get(_mod_key)
    mod = _load_module()
    yield mod
    if prev is None:
        sys.modules.pop(_mod_key, None)
    else:
        sys.modules[_mod_key] = prev


# ── Record structure ─────────────────────────────────────────────────────────


def test_log_record_has_required_fields(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.log("test_event", actor="user@example.com")
    assert "ts" in record
    assert record["event"] == "test_event"
    assert record["actor"] == "user@example.com"
    assert record["outcome"] == "ok"


def test_log_record_includes_detail(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.log("test_event", actor="u", detail={"key": "value"})
    assert record["detail"]["key"] == "value"


def test_log_record_omits_detail_when_none(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.log("test_event", actor="u")
    assert "detail" not in record


def test_ts_is_iso8601(al, tmp_path):
    from datetime import datetime
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.log("ping", actor="test")
    # Should parse without error
    dt = datetime.fromisoformat(record["ts"])
    assert dt.tzinfo is not None  # timezone-aware


# ── File persistence ──────────────────────────────────────────────────────────


def test_writes_ndjson_to_file(al, tmp_path):
    log_path = tmp_path / "audit.ndjson"
    logger = al.AuditLogger(log_path)
    logger.log("ping", actor="a")
    logger.log("pong", actor="b")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event"] == "ping"
    assert json.loads(lines[1])["event"] == "pong"


def test_creates_parent_directories(al, tmp_path):
    log_path = tmp_path / "deep" / "nested" / "audit.ndjson"
    logger = al.AuditLogger(log_path)
    logger.log("ping", actor="a")
    assert log_path.exists()


def test_appends_on_successive_calls(al, tmp_path):
    log_path = tmp_path / "audit.ndjson"
    logger = al.AuditLogger(log_path)
    for i in range(5):
        logger.log("event", actor=f"user{i}")
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5


# ── Stream mirroring ──────────────────────────────────────────────────────────


def test_mirrors_to_stream(al):
    buf = io.StringIO()
    logger = al.AuditLogger(stream=buf)
    logger.log("test", actor="stream-only")
    buf.seek(0)
    record = json.loads(buf.read())
    assert record["event"] == "test"


def test_stream_and_file_both_written(al, tmp_path):
    buf = io.StringIO()
    log_path = tmp_path / "audit.ndjson"
    logger = al.AuditLogger(log_path, stream=buf)
    logger.log("dual", actor="a")
    assert log_path.exists()
    buf.seek(0)
    assert "dual" in buf.read()


# ── High-level event methods ─────────────────────────────────────────────────


def test_query_event(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.query("user", query="medieval texts", collection="latin", results=5)
    assert record["event"] == "query"
    assert record["detail"]["query"] == "medieval texts"
    assert record["detail"]["collection"] == "latin"
    assert record["detail"]["results"] == 5


def test_ingest_event(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.ingest("admin", collection="corpus", chunk_count=100, source="data.pdf")
    assert record["event"] == "ingest"
    assert record["detail"]["collection"] == "corpus"
    assert record["detail"]["chunk_count"] == 100
    assert record["detail"]["source"] == "data.pdf"


def test_access_event_ok(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.access("127.0.0.1", resource="/api/search", method="GET", status=200)
    assert record["event"] == "access"
    assert record["outcome"] == "ok"


def test_access_event_error(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.access("127.0.0.1", resource="/api/search", status=500)
    assert record["outcome"] == "error"


def test_admin_event(al, tmp_path):
    logger = al.AuditLogger(tmp_path / "audit.ndjson")
    record = logger.admin("admin", action="collection_reset", target="latin_texts")
    assert record["event"] == "admin"
    assert record["detail"]["action"] == "collection_reset"
    assert record["detail"]["target"] == "latin_texts"


# ── No-path (stream-only) mode ────────────────────────────────────────────────


def test_stream_only_does_not_write_file(al, tmp_path):
    buf = io.StringIO()
    logger = al.AuditLogger(stream=buf)
    logger.log("test", actor="a")
    assert list(tmp_path.iterdir()) == []


# ── CLI ───────────────────────────────────────────────────────────────────────


def test_cli_query_creates_file(al, tmp_path):
    log_path = tmp_path / "audit.ndjson"
    al.main(["--log-path", str(log_path), "--actor", "tester",
              "query", "--query", "hello world"])
    lines = log_path.read_text().strip().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["event"] == "query"
    assert record["detail"]["query"] == "hello world"


def test_cli_ingest(al, tmp_path):
    log_path = tmp_path / "audit.ndjson"
    al.main(["--log-path", str(log_path), "ingest",
              "--collection", "my_corpus", "--chunk-count", "42"])
    record = json.loads(log_path.read_text().strip())
    assert record["event"] == "ingest"
    assert record["detail"]["chunk_count"] == 42


def test_cli_admin(al, tmp_path):
    log_path = tmp_path / "audit.ndjson"
    al.main(["--log-path", str(log_path), "admin",
              "--action", "reset", "--target", "collection_x"])
    record = json.loads(log_path.read_text().strip())
    assert record["event"] == "admin"
    assert record["detail"]["action"] == "reset"


def test_cli_access(al, tmp_path):
    log_path = tmp_path / "audit.ndjson"
    al.main(["--log-path", str(log_path), "access",
              "--resource", "/api/test", "--status", "404"])
    record = json.loads(log_path.read_text().strip())
    assert record["event"] == "access"
    assert record["outcome"] == "error"
