"""Tests for tools/whisper-subtitle/subtitle.py."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SUBTITLE_PY = REPO_ROOT / "tools" / "whisper-subtitle" / "subtitle.py"


@pytest.fixture(scope="module")
def sub():
    _mod_key = "whisper_subtitle_test_module"
    spec = importlib.util.spec_from_file_location(_mod_key, SUBTITLE_PY)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {SUBTITLE_PY}")
    mod = importlib.util.module_from_spec(spec)
    prev = sys.modules.get(_mod_key)
    sys.modules[_mod_key] = mod
    spec.loader.exec_module(mod)
    yield mod
    if prev is None:
        sys.modules.pop(_mod_key, None)
    else:
        sys.modules[_mod_key] = prev


# ---------------------------------------------------------------------------
# Timestamp formatting
# ---------------------------------------------------------------------------


class TestTimestampSrt:
    def test_zero(self, sub):
        assert sub._format_timestamp_srt(0.0) == "00:00:00,000"

    def test_one_hour(self, sub):
        assert sub._format_timestamp_srt(3600.0) == "01:00:00,000"

    def test_milliseconds(self, sub):
        assert sub._format_timestamp_srt(1.5) == "00:00:01,500"

    def test_mixed(self, sub):
        assert sub._format_timestamp_srt(3661.123) == "01:01:01,123"


class TestTimestampVtt:
    def test_uses_dot_not_comma(self, sub):
        assert sub._format_timestamp_vtt(1.5) == "00:00:01.500"

    def test_zero(self, sub):
        assert sub._format_timestamp_vtt(0.0) == "00:00:00.000"


# ---------------------------------------------------------------------------
# Filler word stripping
# ---------------------------------------------------------------------------


class TestStripFiller:
    def test_removes_uh(self, sub):
        assert sub._strip_filler_words("uh hello there") == "hello there"

    def test_removes_um(self, sub):
        assert sub._strip_filler_words("um um the thing") == "the thing"

    def test_removes_hmm(self, sub):
        assert sub._strip_filler_words("hmm interesting") == "interesting"

    def test_case_insensitive(self, sub):
        assert sub._strip_filler_words("UH UH well") == "well"

    def test_preserves_non_filler(self, sub):
        assert sub._strip_filler_words("hello world") == "hello world"

    def test_elongated_uh(self, sub):
        assert sub._strip_filler_words("uhhh okay") == "okay"


# ---------------------------------------------------------------------------
# Segment splitting
# ---------------------------------------------------------------------------


class TestSplitSegment:
    def test_no_split_needed(self, sub):
        cues = sub._split_segment(0.0, 4.0, "hello world", max_words=5)
        assert len(cues) == 1
        assert cues[0].text == "hello world"

    def test_splits_evenly(self, sub):
        cues = sub._split_segment(0.0, 4.0, "one two three four five six", max_words=3)
        assert len(cues) == 2
        assert cues[0].text == "one two three"
        assert cues[1].text == "four five six"

    def test_splits_timing_evenly(self, sub):
        cues = sub._split_segment(0.0, 6.0, "a b c d e f", max_words=2)
        assert len(cues) == 3
        assert cues[0].start == pytest.approx(0.0)
        assert cues[0].end == pytest.approx(2.0)
        assert cues[1].start == pytest.approx(2.0)

    def test_remainder_chunk(self, sub):
        cues = sub._split_segment(0.0, 5.0, "one two three four five", max_words=3)
        assert len(cues) == 2
        assert cues[0].text == "one two three"
        assert cues[1].text == "four five"

    def test_zero_max_words_raises(self, sub):
        with pytest.raises(ValueError, match="positive integer"):
            sub._split_segment(0.0, 4.0, "hello world", max_words=0)

    def test_negative_max_words_raises(self, sub):
        with pytest.raises(ValueError, match="positive integer"):
            sub._split_segment(0.0, 4.0, "hello world", max_words=-1)


# ---------------------------------------------------------------------------
# segments_to_cues
# ---------------------------------------------------------------------------


class TestSegmentsToCues:
    def _seg(self, start, end, text):
        return {"start": start, "end": end, "text": text}

    def test_basic_conversion(self, sub):
        cues = sub.segments_to_cues([self._seg(0, 2, "hello world")])
        assert len(cues) == 1
        assert cues[0].text == "hello world"
        assert cues[0].start == 0.0
        assert cues[0].end == 2.0

    def test_skips_empty_text(self, sub):
        segs = [self._seg(0, 2, ""), self._seg(2, 4, "real text")]
        cues = sub.segments_to_cues(segs)
        assert len(cues) == 1
        assert cues[0].text == "real text"

    def test_normalises_whitespace(self, sub):
        cues = sub.segments_to_cues([self._seg(0, 2, "  hello   world  ")])
        assert cues[0].text == "hello world"

    def test_strip_filler(self, sub):
        cues = sub.segments_to_cues(
            [self._seg(0, 2, "uh hello um world")],
            strip_filler=True,
        )
        assert cues[0].text == "hello world"

    def test_max_words(self, sub):
        cues = sub.segments_to_cues(
            [self._seg(0, 6, "one two three four five six")],
            max_words=3,
        )
        assert len(cues) == 2

    def test_inverted_timestamps_skipped(self, sub):
        segs = [self._seg(5, 3, "bad"), self._seg(3, 5, "good")]
        cues = sub.segments_to_cues(segs)
        assert len(cues) == 1
        assert cues[0].text == "good"


# ---------------------------------------------------------------------------
# SRT / VTT output
# ---------------------------------------------------------------------------


class TestCuesToSrt:
    def test_basic_srt(self, sub):
        cues = [sub.Cue(start=0.0, end=2.5, text="Hello world")]
        output = sub.cues_to_srt(cues)
        assert "1\n" in output
        assert "00:00:00,000 --> 00:00:02,500" in output
        assert "Hello world" in output

    def test_multiple_cues_numbered(self, sub):
        cues = [
            sub.Cue(start=0.0, end=1.0, text="First"),
            sub.Cue(start=1.0, end=2.0, text="Second"),
        ]
        output = sub.cues_to_srt(cues)
        assert "1\n" in output
        assert "2\n" in output

    def test_empty_cues(self, sub):
        assert sub.cues_to_srt([]) == ""


class TestCuesToVtt:
    def test_starts_with_webvtt(self, sub):
        cues = [sub.Cue(start=0.0, end=1.0, text="Hi")]
        output = sub.cues_to_vtt(cues)
        assert output.startswith("WEBVTT")

    def test_uses_dot_separator(self, sub):
        cues = [sub.Cue(start=0.0, end=1.5, text="Hi")]
        output = sub.cues_to_vtt(cues)
        assert "00:00:01.500" in output
        assert "," not in output.split("\n", 2)[2]  # no comma in timestamps


class TestConvertOutputFormat:
    def test_unknown_format_raises(self, sub, tmp_path):
        data = {"segments": [{"start": 0.0, "end": 1.0, "text": "hi"}]}
        path = tmp_path / "t.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="Unsupported output_format"):
            sub.convert(path, output_format="xml")

    def test_convert_srt_output(self, sub, tmp_path):
        data = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}
        path = tmp_path / "t.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = sub.convert(path, output_format="srt")
        assert "00:00:00,000 --> 00:00:01,000" in result
        assert "Hello world" in result

    def test_convert_vtt_output(self, sub, tmp_path):
        data = {"segments": [{"start": 0.0, "end": 1.0, "text": "Hello world"}]}
        path = tmp_path / "t.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        result = sub.convert(path, output_format="vtt")
        assert result.startswith("WEBVTT")


# ---------------------------------------------------------------------------
# load_whisper_json
# ---------------------------------------------------------------------------


class TestLoadWhisperJson:
    def test_loads_dict_format(self, sub, tmp_path):
        data = {
            "text": "hello world",
            "segments": [
                {"start": 0.0, "end": 2.0, "text": "hello world"}
            ],
        }
        path = tmp_path / "transcript.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        segs = sub.load_whisper_json(path)
        assert len(segs) == 1
        assert segs[0]["text"] == "hello world"

    def test_loads_list_format(self, sub, tmp_path):
        data = [{"start": 0.0, "end": 2.0, "text": "hello"}]
        path = tmp_path / "transcript.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        segs = sub.load_whisper_json(path)
        assert len(segs) == 1

    def test_empty_segments_returns_empty(self, sub, tmp_path):
        data = {"text": "", "segments": []}
        path = tmp_path / "transcript.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        assert sub.load_whisper_json(path) == []

    def test_invalid_shape_raises(self, sub, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text(json.dumps("just a string"), encoding="utf-8")
        with pytest.raises(ValueError, match="Unexpected"):
            sub.load_whisper_json(path)

    def test_missing_fields_raises(self, sub, tmp_path):
        data = {"segments": [{"start": 0.0}]}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="missing"):
            sub.load_whisper_json(path)

    def test_second_segment_missing_fields_raises(self, sub, tmp_path):
        data = {"segments": [
            {"start": 0.0, "end": 2.0, "text": "ok"},
            {"start": 2.0},
        ]}
        path = tmp_path / "bad.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ValueError, match="Segment 1"):
            sub.load_whisper_json(path)

    def test_null_segments_raises(self, sub, tmp_path):
        """{'segments': null} must raise ValueError, not silently return []."""
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({"segments": None}), encoding="utf-8")
        with pytest.raises(ValueError, match="null"):
            sub.load_whisper_json(path)

    def test_missing_segments_key_raises(self, sub, tmp_path):
        """A dict with no 'segments' key must raise ValueError."""
        path = tmp_path / "bad.json"
        path.write_text(json.dumps({}), encoding="utf-8")
        with pytest.raises(ValueError):
            sub.load_whisper_json(path)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


class TestCLI:
    def test_default_format_is_srt(self, sub):
        parser = sub._build_parser()
        args = parser.parse_args(["transcript.json"])
        assert args.output_format == "srt"

    def test_vtt_format(self, sub):
        parser = sub._build_parser()
        args = parser.parse_args(["transcript.json", "--format", "vtt"])
        assert args.output_format == "vtt"

    def test_max_words(self, sub):
        parser = sub._build_parser()
        args = parser.parse_args(["transcript.json", "--max-words", "5"])
        assert args.max_words == 5

    def test_strip_filler_flag(self, sub):
        parser = sub._build_parser()
        args = parser.parse_args(["transcript.json", "--strip-filler"])
        assert args.strip_filler is True
