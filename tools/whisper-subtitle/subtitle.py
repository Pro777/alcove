#!/usr/bin/env python3
"""Whisper JSON → SRT/VTT subtitle generator.

Converts OpenAI Whisper transcription output (JSON with per-segment timestamps)
into standard subtitle files. Supports SRT and WebVTT output formats and optional
per-word caption splitting for shorter on-screen durations.

Usage::

    # Convert Whisper JSON to SRT
    python tools/whisper-subtitle/subtitle.py transcript.json -o subtitles.srt

    # Convert to WebVTT
    python tools/whisper-subtitle/subtitle.py transcript.json --format vtt -o subtitles.vtt

    # Split long segments into shorter captions (max 8 words per cue)
    python tools/whisper-subtitle/subtitle.py transcript.json --max-words 8

    # Write to stdout
    python tools/whisper-subtitle/subtitle.py transcript.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Cue:
    """A single subtitle cue (one time-stamped text block)."""

    start: float  # seconds
    end: float    # seconds
    text: str


# ---------------------------------------------------------------------------
# Whisper JSON parsing
# ---------------------------------------------------------------------------


def load_whisper_json(path: Path) -> list[dict]:
    """Load Whisper transcription JSON and return the segments list.

    Args:
        path: Path to a Whisper JSON output file.

    Returns:
        List of segment dicts, each with at least ``start``, ``end``, ``text``.

    Raises:
        ValueError: If the file does not look like Whisper output.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        # Some Whisper variants output a bare list of segments
        segments = data
    elif isinstance(data, dict):
        segments = data.get("segments")
        if not isinstance(segments, list):
            raise ValueError(
                f"Expected top-level 'segments' list, got "
                f"{type(segments).__name__ if segments is not None else 'null'}"
            )
    else:
        raise ValueError(f"Unexpected Whisper JSON shape: {type(data)}")

    if not segments:
        return []

    # Validate every segment has required fields
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            raise ValueError(f"Segment {i} must be a dict, got {type(seg).__name__}")
        missing = [k for k in ("start", "end", "text") if k not in seg]
        if missing:
            raise ValueError(
                f"Segment {i} missing required fields {missing}. "
                f"Got keys: {list(seg.keys())}"
            )
    return segments


def segments_to_cues(
    segments: list[dict],
    *,
    max_words: int | None = None,
    strip_filler: bool = False,
) -> list[Cue]:
    """Convert Whisper segments to Cue objects.

    Args:
        segments: List of Whisper segment dicts.
        max_words: If set, split segments with more than this many words into
            shorter cues of equal duration.
        strip_filler: Remove common filler words (``uh``, ``um``, ``hmm``).

    Returns:
        List of :class:`Cue` objects ready for serialisation.
    """
    cues: list[Cue] = []
    for seg in segments:
        start = float(seg["start"])
        end = float(seg["end"])
        if end < start:
            continue  # skip malformed segments with inverted timestamps
        text = seg.get("text", "").strip()

        if strip_filler:
            text = _strip_filler_words(text)

        text = " ".join(text.split())  # normalise whitespace
        if not text:
            continue

        if max_words is not None:
            cues.extend(_split_segment(start, end, text, max_words))
        else:
            cues.append(Cue(start=start, end=end, text=text))

    return cues


_FILLER_RE = re.compile(r"\b(uh+|um+|hmm+|hm+|mhm+)\b", re.IGNORECASE)


def _strip_filler_words(text: str) -> str:
    cleaned = _FILLER_RE.sub("", text)
    return " ".join(cleaned.split())


def _split_segment(start: float, end: float, text: str, max_words: int) -> list[Cue]:
    """Split a single segment into cues of at most *max_words* words."""
    if max_words <= 0:
        raise ValueError(f"max_words must be a positive integer, got {max_words!r}")
    words = text.split()
    if len(words) <= max_words:
        return [Cue(start=start, end=end, text=text)]

    duration = end - start
    chunks: list[list[str]] = []
    for i in range(0, len(words), max_words):
        chunks.append(words[i : i + max_words])

    cues: list[Cue] = []
    chunk_dur = duration / len(chunks)
    for idx, chunk in enumerate(chunks):
        cue_start = start + idx * chunk_dur
        cue_end = cue_start + chunk_dur
        cues.append(Cue(start=cue_start, end=cue_end, text=" ".join(chunk)))

    return cues


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as ``HH:MM:SS,mmm`` (SRT)."""
    ms = round(seconds * 1000)
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1_000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as ``HH:MM:SS.mmm`` (WebVTT)."""
    return _format_timestamp_srt(seconds).replace(",", ".")


def cues_to_srt(cues: list[Cue]) -> str:
    """Serialise cues to SRT format string."""
    lines: list[str] = []
    for i, cue in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(
            f"{_format_timestamp_srt(cue.start)} --> {_format_timestamp_srt(cue.end)}"
        )
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines)


def cues_to_vtt(cues: list[Cue]) -> str:
    """Serialise cues to WebVTT format string."""
    lines: list[str] = ["WEBVTT", ""]
    for cue in cues:
        lines.append(
            f"{_format_timestamp_vtt(cue.start)} --> {_format_timestamp_vtt(cue.end)}"
        )
        lines.append(cue.text)
        lines.append("")
    return "\n".join(lines)


def convert(
    input_path: Path,
    *,
    output_format: str = "srt",
    max_words: int | None = None,
    strip_filler: bool = False,
) -> str:
    """Full pipeline: load JSON → parse → format.

    Args:
        input_path: Path to Whisper JSON output.
        output_format: ``"srt"`` or ``"vtt"``.
        max_words: Optional per-cue word limit.
        strip_filler: Whether to remove filler words.

    Returns:
        Subtitle file content as a string.
    """
    segments = load_whisper_json(input_path)
    cues = segments_to_cues(segments, max_words=max_words, strip_filler=strip_filler)

    if output_format == "srt":
        return cues_to_srt(cues)
    if output_format == "vtt":
        return cues_to_vtt(cues)
    raise ValueError(f"Unsupported output_format {output_format!r}. Use 'srt' or 'vtt'.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert Whisper JSON transcription to SRT or WebVTT subtitles.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, help="Whisper JSON transcription file")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output file (default: stdout)",
    )
    parser.add_argument(
        "--format", dest="output_format", choices=["srt", "vtt"], default="srt",
        help="Output subtitle format (default: srt)",
    )
    parser.add_argument(
        "--max-words", type=int, default=None, metavar="N",
        help="Split long segments into cues of at most N words (must be >= 1)",
    )
    parser.add_argument(
        "--strip-filler", action="store_true",
        help="Remove filler words (uh, um, hmm)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.max_words is not None and args.max_words <= 0:
        parser.error(f"--max-words must be a positive integer, got {args.max_words}")

    result = convert(
        args.input,
        output_format=args.output_format,
        max_words=args.max_words,
        strip_filler=args.strip_filler,
    )

    if args.output:
        args.output.write_text(result, encoding="utf-8")
        print(f"Wrote {args.output}", file=sys.stderr)
    else:
        print(result, end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
