"""Tests for tools/asl-gloss/gloss.py."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GLOSS_PY = REPO_ROOT / "tools" / "asl-gloss" / "gloss.py"


@pytest.fixture(scope="module")
def gloss():
    _mod_key = "asl_gloss_test_module"
    spec = importlib.util.spec_from_file_location(_mod_key, GLOSS_PY)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {GLOSS_PY}")
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get(_mod_key)
    sys.modules[_mod_key] = mod
    spec.loader.exec_module(mod)
    yield mod
    if prev is None:
        sys.modules.pop(_mod_key, None)
    else:
        sys.modules[_mod_key] = prev


@pytest.fixture(scope="module")
def converter(gloss):
    return gloss.GlossConverter()


# ---------------------------------------------------------------------------
# _detect_question_type
# ---------------------------------------------------------------------------


class TestDetectQuestionType:
    def test_yn_question(self, gloss):
        assert gloss._detect_question_type("Do you want coffee?") == "yn"

    def test_wh_question_what(self, gloss):
        assert gloss._detect_question_type("What do you want?") == "wh"

    def test_wh_question_where(self, gloss):
        assert gloss._detect_question_type("Where is the library?") == "wh"

    def test_non_question(self, gloss):
        assert gloss._detect_question_type("The cat sat.") is None

    def test_statement_with_question_mark_edge(self, gloss):
        assert gloss._detect_question_type("Really?") == "yn"


# ---------------------------------------------------------------------------
# _expand_negations
# ---------------------------------------------------------------------------


class TestExpandNegations:
    def test_dont(self, gloss):
        assert "do not" in gloss._expand_negations("I don't want it")

    def test_cant(self, gloss):
        assert "can not" in gloss._expand_negations("I can't go")

    def test_doesnt(self, gloss):
        assert "does not" in gloss._expand_negations("She doesn't like it")

    def test_doesnt_exact(self, gloss):
        assert gloss._expand_negations("She doesn't like it") == "She does not like it"

    def test_wont_exact(self, gloss):
        assert gloss._expand_negations("I won't go") == "I will not go"

    def test_do_question_no_negation_unchanged(self, gloss):
        text = "Do you want coffee?"
        assert gloss._expand_negations(text) == text

    def test_no_negation_unchanged(self, gloss):
        text = "I want coffee"
        assert gloss._expand_negations(text) == text

    def test_temporal_unchanged(self, gloss):
        text = "I went last week"
        assert gloss._expand_negations(text) == text


# ---------------------------------------------------------------------------
# Article removal
# ---------------------------------------------------------------------------


class TestArticleRemoval:
    def test_removes_the(self, converter):
        result = converter.convert("The cat sat on the mat.")
        assert "THE" not in result.gloss

    def test_removes_a(self, converter):
        result = converter.convert("A dog barked.")
        tokens = result.tokens
        assert "A" not in tokens

    def test_removes_an(self, converter):
        result = converter.convert("An apple fell.")
        assert "AN" not in result.tokens

    def test_keep_articles_flag(self, gloss):
        c = gloss.GlossConverter(drop_articles=False)
        result = c.convert("The cat sat.")
        assert "THE" in result.tokens


# ---------------------------------------------------------------------------
# Copula removal
# ---------------------------------------------------------------------------


class TestCopulaRemoval:
    def test_removes_is(self, converter):
        result = converter.convert("She is happy.")
        assert "IS" not in result.tokens

    def test_removes_are(self, converter):
        result = converter.convert("They are ready.")
        assert "ARE" not in result.tokens

    def test_keep_copula_flag(self, gloss):
        c = gloss.GlossConverter(drop_copula=False)
        result = c.convert("She is happy.")
        assert "IS" in result.tokens


# ---------------------------------------------------------------------------
# Pronoun substitution
# ---------------------------------------------------------------------------


class TestPronounSubstitution:
    def test_i_becomes_me(self, converter):
        result = converter.convert("I want coffee.")
        assert "ME" in result.tokens

    def test_she_stays_she(self, converter):
        result = converter.convert("She wants coffee.")
        assert "SHE" in result.tokens

    def test_they_stays_they(self, converter):
        result = converter.convert("They need help.")
        assert "THEY" in result.tokens


# ---------------------------------------------------------------------------
# Negation
# ---------------------------------------------------------------------------


class TestNegation:
    def test_dont_becomes_not(self, converter):
        result = converter.convert("I don't want coffee.")
        assert "NOT" in result.tokens
        assert "DO" not in result.tokens  # auxiliary must drop

    def test_doesnt_becomes_not_exact(self, converter):
        """SHE DOES NOT LIKE IT must have DOES dropped → SHE NOT LIKE IT."""
        result = converter.convert("She doesn't like it.")
        assert "NOT" in result.tokens
        assert "DOES" not in result.tokens  # does drops as auxiliary
        assert result.gloss == "SHE NOT LIKE IT"

    def test_wont_exact(self, converter):
        """I won't go. → ME NOT GO (will auxiliary drops after expansion)."""
        result = converter.convert("I won't go.")
        assert "NOT" in result.tokens
        assert "WILL" not in result.tokens  # will drops as auxiliary
        assert result.gloss == "ME NOT GO"

    def test_cant_becomes_not(self, converter):
        result = converter.convert("I can't go.")
        assert "NOT" in result.tokens


# ---------------------------------------------------------------------------
# Question markers
# ---------------------------------------------------------------------------


class TestYNQuestion:
    def test_yn_marker_added(self, converter):
        result = converter.convert("Do you want coffee?")
        assert "Y/N" in result.tokens
        assert any("Y/N" in n for n in result.notes)

    def test_yn_do_auxiliary_drops(self, converter):
        """Do you want coffee? must not contain DO — it's a question-forming auxiliary."""
        result = converter.convert("Do you want coffee?")
        assert "DO" not in result.tokens
        assert result.gloss == "YOU WANT COFFEE Y/N"

    def test_yn_note_present(self, converter):
        result = converter.convert("Is she here?")
        assert any("Y/N" in n for n in result.notes)


class TestWhQuestion:
    def test_wh_word_moves_to_end(self, converter):
        result = converter.convert("What do you want?")
        # WHAT should be at or near the end
        assert result.tokens[-1] == "?" or "WHAT" in result.tokens[-3:]

    def test_wh_note_present(self, converter):
        result = converter.convert("Where is the library?")
        assert any("WH" in n for n in result.notes)


# ---------------------------------------------------------------------------
# Temporal fronting
# ---------------------------------------------------------------------------


class TestTemporalFronting:
    def test_yesterday_fronts(self, converter):
        result = converter.convert("I went to the store yesterday.")
        # YESTERDAY should be first (or near first) token
        assert result.tokens[0] == "YESTERDAY"

    def test_tomorrow_fronts(self, converter):
        result = converter.convert("She will come tomorrow.")
        assert result.tokens[0] == "TOMORROW"

    def test_last_week_phrase_fronts(self, converter):
        """'last week' is a two-word temporal that must front as a phrase."""
        result = converter.convert("I left last week.")
        assert result.tokens[0] == "LAST WEEK"
        # Neither LAST nor WEEK should appear again later in the sequence
        assert result.tokens.count("LAST WEEK") == 1


# ---------------------------------------------------------------------------
# convert_batch
# ---------------------------------------------------------------------------


class TestConvertBatch:
    def test_batch_length(self, converter):
        results = converter.convert_batch(["Hello.", "Goodbye.", "See you."])
        assert len(results) == 3

    def test_batch_preserves_source(self, converter):
        texts = ["Hello world.", "Goodbye."]
        results = converter.convert_batch(texts)
        assert results[0].source == "Hello world."
        assert results[1].source == "Goodbye."


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatText:
    def test_includes_en_and_asl_lines(self, gloss, converter):
        results = [converter.convert("The cat sat.")]
        text = gloss.format_text(results)
        assert "EN:" in text
        assert "ASL:" in text

    def test_notes_included_when_present(self, gloss, converter):
        results = [converter.convert("Do you want coffee?")]
        text = gloss.format_text(results)
        assert "Y/N" in text


class TestFormatJson:
    def test_json_structure(self, gloss, converter):
        results = [converter.convert("The cat sat.")]
        output = json.loads(gloss.format_json(results))
        assert len(output) == 1
        assert "source" in output[0]
        assert "gloss" in output[0]
        assert "tokens" in output[0]
        assert "notes" in output[0]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCLI:
    def test_default_format_is_text(self, gloss):
        parser = gloss._build_parser()
        args = parser.parse_args(["Hello world."])
        assert args.output_format == "text"

    def test_json_format(self, gloss):
        parser = gloss._build_parser()
        args = parser.parse_args(["--format", "json", "Hello."])
        assert args.output_format == "json"

    def test_keep_articles(self, gloss):
        parser = gloss._build_parser()
        args = parser.parse_args(["--keep-articles", "The cat."])
        assert args.keep_articles is True

    def test_file_arg(self, gloss, tmp_path):
        path = tmp_path / "sentences.txt"
        path.write_text("Hello.\nGoodbye.\n", encoding="utf-8")
        parser = gloss._build_parser()
        args = parser.parse_args(["--file", str(path)])
        assert args.file == path

    def test_text_and_file_mutually_exclusive(self, gloss):
        parser = gloss._build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["Hello.", "--file", "sentences.txt"])
