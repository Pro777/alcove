"""Tests for tools/congress-ingest/ingest_bills.py pure functions."""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

# Import module under test using importlib to avoid package install requirement
import importlib.util
import sys

_MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "congress-ingest" / "ingest_bills.py"


def _load_module():
    _mod_key = "ingest_bills_test_module"
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
def ib():
    _mod_key = "ingest_bills_test_module"
    prev = sys.modules.get(_mod_key)
    mod = _load_module()
    yield mod
    if prev is None:
        sys.modules.pop(_mod_key, None)
    else:
        sys.modules[_mod_key] = prev


# ── strip_html ──────────────────────────────────────────────────────────────


def test_strip_html_removes_tags(ib):
    assert ib.strip_html("<p>Hello <b>world</b></p>") == "Hello world"


def test_strip_html_decodes_entities(ib):
    assert ib.strip_html("&amp; &lt;tag&gt;") == "& <tag>"


def test_strip_html_collapses_whitespace(ib):
    assert ib.strip_html("  a   b\t c  ") == "a b c"


def test_strip_html_empty_string(ib):
    assert ib.strip_html("") == ""


def test_strip_html_none_like(ib):
    assert ib.strip_html(None) == ""  # type: ignore[arg-type]


# ── normalize_summary_identity ───────────────────────────────────────────────


def test_normalize_uses_attrs_when_no_id(ib):
    norm_id, ver = ib.normalize_summary_identity(None, congress=118, bill_type="hr", bill_number=1)
    assert norm_id == "billsum-118-hr-1-v00"
    assert ver == "v00"


def test_normalize_parses_full_id(ib):
    # Pattern: id<congress><bill_type><bill_number><version>
    norm_id, _ver = ib.normalize_summary_identity(
        "id118hr42v1", congress=0, bill_type="x", bill_number=0
    )
    assert "118" in norm_id
    assert "hr" in norm_id
    assert "v1" in norm_id


def test_normalize_extracts_trailing_version(ib):
    _, _ver = ib.normalize_summary_identity("someid-v3", congress=118, bill_type="s", bill_number=5)
    assert _ver == "v3"


# ── version_sort_key ─────────────────────────────────────────────────────────


def test_version_sort_key_numeric(ib):
    assert ib.version_sort_key("v2") > ib.version_sort_key("v1")


def test_version_sort_key_non_numeric_first(ib):
    numeric, _ = ib.version_sort_key("v1")
    non_numeric, _ = ib.version_sort_key("intro")
    assert numeric > non_numeric  # numeric versions rank higher


# ── parse_congresses ─────────────────────────────────────────────────────────


def test_parse_congresses_single(ib):
    assert ib.parse_congresses("118") == [118]


def test_parse_congresses_all(ib):
    result = ib.parse_congresses("all")
    assert 113 in result
    assert 119 in result


def test_parse_congresses_invalid(ib):
    with pytest.raises(ValueError, match="integer"):
        ib.parse_congresses("notanumber")


# ── parse_billsum_xml ─────────────────────────────────────────────────────────

_MINIMAL_XML = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <BillSummarizationBulkData>
      <item congress="118" measure-type="hr" measure-number="1"
            originChamber="H" orig-publish-date="2023-01-10" update-date="2023-06-01">
        <title>A bill to do things</title>
        <summary summary-id="id118hrv1" currentChamber="H">
          <action-date>2023-01-10</action-date>
          <action-desc>Introduced in House</action-desc>
          <summary-text>This bill does things and stuff.</summary-text>
        </summary>
        <summary summary-id="id118hrv2" currentChamber="H">
          <action-date>2023-03-01</action-date>
          <action-desc>Passed House</action-desc>
          <summary-text>This bill, as passed, does more things.</summary-text>
        </summary>
      </item>
    </BillSummarizationBulkData>
""")


def test_parse_billsum_xml_returns_chunks(ib):
    chunks = ib.parse_billsum_xml(_MINIMAL_XML.encode(), source_name="test.xml")
    assert len(chunks) == 2


def test_parse_billsum_xml_metadata_fields(ib):
    chunks = ib.parse_billsum_xml(_MINIMAL_XML.encode(), source_name="test.xml")
    meta = chunks[0].metadata
    assert meta["congress"] == 118
    assert meta["bill_type"] == "hr"
    assert meta["bill_number"] == 1
    assert "url" in meta


def test_parse_billsum_xml_marks_latest(ib):
    chunks = ib.parse_billsum_xml(_MINIMAL_XML.encode(), source_name="test.xml")
    latest = [c for c in chunks if c.metadata["is_latest"]]
    assert len(latest) == 1
    # v2 is latest
    assert "v2" in latest[0].id


def test_parse_billsum_xml_skips_empty_text(ib):
    xml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <BillSummarizationBulkData>
          <item congress="118" measure-type="hr" measure-number="2">
            <title>Empty summary</title>
            <summary summary-id="id118hrv1">
              <summary-text></summary-text>
            </summary>
          </item>
        </BillSummarizationBulkData>
    """)
    chunks = ib.parse_billsum_xml(xml.encode(), source_name="empty.xml")
    assert chunks == []


def test_parse_billsum_xml_skips_invalid_items(ib):
    xml = textwrap.dedent("""\
        <?xml version="1.0" encoding="UTF-8"?>
        <BillSummarizationBulkData>
          <item congress="" measure-type="" measure-number="">
            <summary><summary-text>Should be skipped</summary-text></summary>
          </item>
        </BillSummarizationBulkData>
    """)
    chunks = ib.parse_billsum_xml(xml.encode(), source_name="bad.xml")
    assert chunks == []


# ── StateStore ───────────────────────────────────────────────────────────────


def test_state_store_round_trip(ib, tmp_path):
    path = tmp_path / "state.json"
    store = ib.StateStore(path)
    assert not store.contains("key1")
    store.mark_completed("key1")
    assert store.contains("key1")
    # Reload from disk
    store2 = ib.StateStore(path)
    assert store2.contains("key1")


def test_state_store_reset(ib, tmp_path):
    path = tmp_path / "state.json"
    store = ib.StateStore(path)
    store.mark_completed("key1")
    store.reset()
    assert not store.contains("key1")
    assert not path.exists()


# ── URL builders ─────────────────────────────────────────────────────────────


def test_build_bundle_url(ib):
    url = ib.build_bundle_url(118, "hr")
    assert "govinfo.gov" in url
    assert "118" in url
    assert "hr" in url


def test_build_bill_details_url(ib):
    url = ib.build_bill_details_url(118, "hr", 1)
    assert "govinfo.gov" in url
    assert "details" in url


# ── default_state_path ────────────────────────────────────────────────────────


def test_default_state_path(ib, tmp_path):
    chroma_path = tmp_path / "chroma"
    sp = ib.default_state_path(chroma_path)
    assert sp.parent == tmp_path
    assert sp.name.endswith(".json")
