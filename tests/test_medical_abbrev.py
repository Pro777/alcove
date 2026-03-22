"""Tests for tools/medical-abbrev/expand.py (alcove#65)."""
from __future__ import annotations

import importlib.util
import sys
from io import StringIO
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Hermetic module load
# ---------------------------------------------------------------------------
_TOOL_PATH = (
    Path(__file__).resolve().parent.parent
    / "tools" / "medical-abbrev" / "expand.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("medical_abbrev", _TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["medical_abbrev"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

expand_text = _mod.expand_text
expand_query = _mod.expand_query
list_abbrevs = _mod.list_abbrevs
main = _mod.main
ABBREVS = _mod.ABBREVS


# ---------------------------------------------------------------------------
# expand_text
# ---------------------------------------------------------------------------

class TestExpandText:
    def test_single_abbreviation(self):
        assert "shortness of breath" in expand_text("patient has SOB")

    def test_multiple_abbreviations(self):
        result = expand_text("HTN and DM2")
        assert "hypertension" in result
        assert "type 2 diabetes mellitus" in result

    def test_case_insensitive_match(self):
        result_upper = expand_text("SOB")
        result_lower = expand_text("sob")
        assert "shortness of breath" in result_upper
        assert "shortness of breath" in result_lower

    def test_no_abbreviation_unchanged(self):
        text = "the patient is stable"
        assert expand_text(text) == text

    def test_word_boundary_respected(self):
        # "AMINO" contains "MI" but should not expand it
        result = expand_text("amino acids")
        assert "myocardial infarction" not in result

    def test_slash_abbreviation_nv(self):
        result = expand_text("c/o N/V")
        assert "nausea" in result

    def test_expansion_lowercase_by_default(self):
        result = expand_text("HTN")
        assert result == result.lower()

    def test_custom_abbrev_dict(self):
        custom = {"XYZ": "experimental abbreviation"}
        result = expand_text("patient has XYZ", abbrevs=custom)
        assert "experimental abbreviation" in result

    def test_custom_dict_does_not_expand_default_abbrevs(self):
        custom = {"XYZ": "experimental"}
        result = expand_text("patient has HTN", abbrevs=custom)
        assert "HTN" in result  # not expanded — not in custom dict

    def test_mixed_text_and_abbreviations(self):
        result = expand_text("Pt c/o SOB and HTN")
        assert "patient" in result or "Pt" in result  # "PT" expands to "patient"
        assert "shortness of breath" in result
        assert "hypertension" in result

    def test_acronym_at_end_of_sentence(self):
        result = expand_text("rule out MI")
        assert "myocardial infarction" in result

    def test_utis_plural_boundary(self):
        # "UTI" should expand; "UTILS" should not (word boundary)
        result = expand_text("multiple UTI episodes")
        assert "urinary tract infection" in result


class TestExpandTextPreserveCase:
    def test_preserve_case_uppercase_input(self):
        result = expand_text("HTN", preserve_case=True)
        # with preserve_case=True and uppercase token, expansion should be uppercased
        assert "HYPERTENSION" in result


# ---------------------------------------------------------------------------
# expand_query
# ---------------------------------------------------------------------------

class TestExpandQuery:
    def test_appends_expansion_by_default(self):
        result = expand_query("SOB")
        assert "SOB" in result
        assert "shortness of breath" in result

    def test_no_duplicates(self):
        result = expand_query("SOB SOB")
        words = result.lower().split()
        assert words.count("shortness") == 1

    def test_replace_mode_removes_abbreviation(self):
        result = expand_query("SOB", include_original=False)
        assert "shortness of breath" in result
        # Original abbreviated token should not appear as a standalone word
        tokens = result.split()
        assert "SOB" not in tokens

    def test_non_abbrev_word_passed_through(self):
        result = expand_query("chest pain SOB")
        assert "chest" in result
        assert "pain" in result
        assert "shortness of breath" in result

    def test_expand_query_deduplicates_across_abbrevs(self):
        # DM and DM2 both expand to include "diabetes" and "mellitus"
        result = expand_query("DM DM2")
        words = result.lower().split()
        # "diabetes" should appear no more than twice
        assert words.count("diabetes") <= 2

    def test_custom_abbrevs(self):
        custom = {"ABX": "antibiotics"}
        result = expand_query("patient on ABX", abbrevs=custom)
        assert "antibiotics" in result

    def test_empty_query(self):
        result = expand_query("")
        assert result == ""

    def test_query_with_only_whitespace(self):
        result = expand_query("   ")
        assert result.strip() == ""


# ---------------------------------------------------------------------------
# list_abbrevs
# ---------------------------------------------------------------------------

class TestListAbbrevs:
    def test_returns_list_of_dicts(self):
        result = list_abbrevs()
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_each_entry_has_abbrev_and_expansion(self):
        for entry in list_abbrevs():
            assert "abbrev" in entry
            assert "expansion" in entry

    def test_sorted_alphabetically(self):
        abbrevs = [e["abbrev"] for e in list_abbrevs()]
        assert abbrevs == sorted(abbrevs)

    def test_prefix_filter(self):
        results = list_abbrevs(prefix="DM")
        assert all(r["abbrev"].startswith("DM") for r in results)

    def test_prefix_case_insensitive(self):
        upper = list_abbrevs(prefix="DM")
        lower = list_abbrevs(prefix="dm")
        assert len(upper) == len(lower)

    def test_unknown_prefix_returns_empty(self):
        assert list_abbrevs(prefix="ZZZZZZ") == []

    def test_custom_dict(self):
        custom = {"TEST1": "test expansion one", "TEST2": "test expansion two"}
        result = list_abbrevs(abbrevs=custom)
        assert len(result) == 2

    def test_coverage_includes_key_categories(self):
        """Spot-check that important medical abbreviations are present."""
        abbrev_keys = {e["abbrev"] for e in list_abbrevs()}
        must_include = {"HTN", "DM", "MI", "SOB", "UTI", "CHF", "COPD", "BID", "PRN"}
        for key in must_include:
            assert key in abbrev_keys, f"{key} missing from ABBREVS"


# ---------------------------------------------------------------------------
# ABBREVS dict sanity
# ---------------------------------------------------------------------------

class TestAbbrevDict:
    def test_all_keys_are_uppercase(self):
        for k in ABBREVS:
            assert k == k.upper(), f"Key {k!r} is not uppercase"

    def test_all_values_are_nonempty_strings(self):
        for k, v in ABBREVS.items():
            assert isinstance(v, str) and v.strip(), f"Empty expansion for {k!r}"

    def test_at_least_100_abbreviations(self):
        assert len(ABBREVS) >= 100

    def test_no_duplicate_keys(self):
        # Python silently resolves duplicate dict keys at import time, so we
        # must parse the source AST to catch raw duplicates in the literal.
        import ast

        source = _TOOL_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        keys: list[str] = []
        for node in ast.walk(tree):
            # Find the ABBREVS assignment: `ABBREVS: dict[...] = {...}`
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "ABBREVS"
                and isinstance(node.value, ast.Dict)
            ):
                for key_node in node.value.keys:
                    if isinstance(key_node, ast.Constant):
                        keys.append(key_node.value)
                break
        assert keys, "Could not locate ABBREVS dict in source AST"
        duplicates = [k for k in keys if keys.count(k) > 1]
        assert not duplicates, f"Duplicate keys in ABBREVS literal: {sorted(set(duplicates))}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class TestCli:
    def _run(self, args):
        captured = StringIO()
        old_out = sys.stdout
        sys.stdout = captured
        try:
            ret = main(args)
        finally:
            sys.stdout = old_out
        return ret, captured.getvalue()

    def test_expand_command(self):
        ret, out = self._run(["expand", "--text", "patient has SOB"])
        assert ret == 0
        assert "shortness of breath" in out

    def test_expand_query_command(self):
        ret, out = self._run(["expand-query", "--text", "SOB HTN"])
        assert ret == 0
        assert "shortness of breath" in out
        assert "hypertension" in out

    def test_expand_query_replace_flag(self):
        ret, out = self._run(["expand-query", "--text", "SOB", "--replace"])
        assert ret == 0
        assert "shortness of breath" in out
        assert "SOB" not in out.split()

    def test_list_abbrevs_command(self):
        ret, out = self._run(["list-abbrevs"])
        assert ret == 0
        assert "HTN" in out
        assert "hypertension" in out

    def test_list_abbrevs_prefix(self):
        ret, out = self._run(["list-abbrevs", "--prefix", "DM"])
        assert ret == 0
        lines = [l for l in out.strip().splitlines() if l.strip()]
        assert all("DM" in l for l in lines)
