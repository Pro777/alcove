#!/usr/bin/env python3
"""English → ASL gloss pre-converter.

Converts plain English text into a simplified ASL gloss representation
suitable for review by human interpreters. ASL gloss is a written notation
system that approximates ASL structure using capitalised English words.

This tool applies rule-based transformations commonly used in ASL gloss:
- Article removal (a, an, the)
- Copula reduction (simplified "be" verbs)
- Pronoun substitution (I → ME, we → WE, etc.)
- Negation movement (don't → verb + NOT)
- Yes/no question marker (adds Y/N tag)
- Wh-question marker (moves wh-word to end)
- Temporal adverb fronting (yesterday, tomorrow, etc.)
- Capitalisation of content words

The output is a *starting point* for a human ASL interpreter — not a
production-ready translation.

Usage::

    python tools/asl-gloss/gloss.py "Do you want coffee?"
    python tools/asl-gloss/gloss.py --file sentences.txt
    python tools/asl-gloss/gloss.py --format json "The cat sat on the mat."

Plugin interface::

    # Load directly — directory uses a hyphen so standard package import needs a workaround:
    import importlib.util
    spec = importlib.util.spec_from_file_location("gloss", "tools/asl-gloss/gloss.py")
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    GlossConverter = mod.GlossConverter
    converter = GlossConverter()
    result = converter.convert("She doesn't want coffee.")
    print(result.gloss)  # SHE WANT NOT COFFEE
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GlossResult:
    """Result of a single English → ASL gloss conversion."""

    source: str        # Original English text
    gloss: str         # ASL gloss string
    tokens: list[str]  # Ordered gloss tokens before joining
    notes: list[str]   # Interpreter notes (e.g. "Y/N question detected")


# ---------------------------------------------------------------------------
# Plugin protocol
# ---------------------------------------------------------------------------


class SignLanguagePlugin(Protocol):
    """Protocol for sign language processing plugins.

    Implement this protocol to extend or replace the default gloss converter.
    Compatible with the Alcove plugin system.
    """

    def convert(self, text: str) -> GlossResult:
        """Convert *text* to a gloss result."""
        ...

    def convert_batch(self, texts: list[str]) -> list[GlossResult]:
        """Convert multiple sentences."""
        ...


# ---------------------------------------------------------------------------
# Transformation rules
# ---------------------------------------------------------------------------

# Articles to drop
_ARTICLES = {"a", "an", "the"}

# Pronoun substitutions (subject → object/gloss form)
_PRONOUN_MAP = {
    "i": "ME",
    "me": "ME",
    "we": "WE",
    "us": "US",
    "you": "YOU",
    "he": "HE",
    "she": "SHE",
    "it": "IT",
    "they": "THEY",
    "them": "THEM",
    "my": "MY",
    "your": "YOUR",
    "his": "HIS",
    "her": "HER",
    "its": "ITS",
    "our": "OUR",
    "their": "THEIR",
}

# Temporal adverbs that should front (move to sentence start)
# Single-word temporals are matched per-token; multi-word phrases are matched
# at the text level before tokenization (sorted longest-first).
_TEMPORAL_ADVERBS_SINGLE = {
    "yesterday", "today", "tomorrow", "now", "before",
    "later", "recently", "soon", "already", "finally",
}
_TEMPORAL_PHRASES = [
    "last week", "next week", "last year", "next year",
    "last month", "next month",
]
_TEMPORAL_ADVERBS = _TEMPORAL_ADVERBS_SINGLE  # keep old name for single-token check

# Auxiliary verbs that are dropped in ASL gloss (do/does/did for question
# formation; will/shall as modal auxiliaries — ASL expresses tense lexically)
_AUX_VERBS = {"do", "does", "did", "will", "shall"}

# Wh-question words
_WH_WORDS = {"what", "where", "when", "why", "how", "who", "which", "whom", "whose"}

# Simple copula forms to drop or simplify
_COPULA = {"is", "are", "was", "were", "am", "be", "been", "being"}

# Negation contractions → base verb + NOT
_NEGATION_RE = re.compile(
    # Group 1: verb root + n't (regular pattern)
    r"\b(do|does|did|could|would|should|must|have|has|had|is|are|was|were)(n['\u2019]t)\b"
    # can't / won't / shan't (irregular or 't-only suffix)
    r"|\b(can|won|shan)['\u2019]t\b",
    re.IGNORECASE,
)

# Map contracted forms that don't share the base verb name
_IRREGULAR_CONTRACTION_MAP = {"won": "will", "shan": "shall"}
_WANT_NEG_RE = re.compile(r"\bdon['\u2019]t want\b", re.IGNORECASE)


def _tokenize(text: str) -> list[str]:
    """Split text into word tokens, stripping punctuation."""
    text = text.strip()
    tokens = re.findall(r"[a-zA-Z']+", text)
    return tokens


def _detect_question_type(text: str) -> str | None:
    """Detect question type: ``'yn'``, ``'wh'``, or ``None``."""
    stripped = text.strip()
    if not stripped.endswith("?"):
        return None
    first_word = stripped.split()[0].lower().rstrip("?") if stripped.split() else ""
    if first_word in _WH_WORDS:
        return "wh"
    # Also check if any wh-word is near the start
    words = stripped.split()[:3]
    for w in words:
        if w.lower().rstrip("?,") in _WH_WORDS:
            return "wh"
    return "yn"


def _expand_negations(text: str) -> str:
    """Expand contractions like ``don't`` → ``do not``, ``won't`` → ``will not``."""
    def _expand(m: re.Match) -> str:
        # Group 1: regular verbs (do, does, did, etc.)
        # Group 3: can/won (won → will via _IRREGULAR_CONTRACTION_MAP)
        verb = m.group(1) or m.group(3)
        if verb:
            verb = _IRREGULAR_CONTRACTION_MAP.get(verb.lower(), verb)
        return f"{verb} not"
    return _NEGATION_RE.sub(_expand, text)


# ---------------------------------------------------------------------------
# Core converter
# ---------------------------------------------------------------------------


class GlossConverter:
    """Rule-based English → ASL gloss converter.

    Applies a fixed pipeline of transformations to produce a simplified
    ASL gloss string. Suitable as a starting draft for human interpreters.

    Args:
        drop_articles: Remove articles (a, an, the). Default True.
        drop_copula: Remove copula verbs (is, are, etc.). Default True.
        front_temporals: Move temporal adverbs to start. Default True.
        move_wh: Move wh-word to end of sentence. Default True.
    """

    def __init__(
        self,
        *,
        drop_articles: bool = True,
        drop_copula: bool = True,
        front_temporals: bool = True,
        move_wh: bool = True,
    ) -> None:
        self.drop_articles = drop_articles
        self.drop_copula = drop_copula
        self.front_temporals = front_temporals
        self.move_wh = move_wh

    def convert(self, text: str) -> GlossResult:
        """Convert a single English sentence to ASL gloss.

        Args:
            text: English input sentence.

        Returns:
            :class:`GlossResult` with gloss string, tokens, and notes.
        """
        notes: list[str] = []
        question_type = _detect_question_type(text)

        # Expand negation contractions before tokenisation
        working = _expand_negations(text)

        # Front multi-word temporal phrases at the text level (longest first so
        # "last week" is matched before "last" alone would be checked per-token)
        fronted: list[str] = []
        if self.front_temporals:
            for phrase in _TEMPORAL_PHRASES:
                pattern = re.compile(re.escape(phrase), re.IGNORECASE)
                if pattern.search(working):
                    fronted.append(phrase.upper())
                    working = pattern.sub("", working)

        tokens = _tokenize(working)
        result_tokens: list[str] = []

        for tok in tokens:
            lower = tok.lower()

            # Drop articles
            if self.drop_articles and lower in _ARTICLES:
                continue

            # Drop copula (be-verbs)
            if self.drop_copula and lower in _COPULA:
                continue

            # Drop auxiliary verbs (do/does/did for question formation; will/shall)
            if lower in _AUX_VERBS:
                continue

            # Substitute pronouns
            if lower in _PRONOUN_MAP:
                result_tokens.append(_PRONOUN_MAP[lower])
                continue

            # Single-word temporal adverb fronting
            if self.front_temporals and lower in _TEMPORAL_ADVERBS:
                fronted.append(lower.upper())
                continue

            # Convert "not" to NOT
            if lower == "not":
                result_tokens.append("NOT")
                continue

            # All other content words: uppercase
            result_tokens.append(tok.upper())

        # Front temporal adverbs
        final_tokens: list[str] = fronted + result_tokens

        # Wh-question: move wh-word to end
        if question_type == "wh" and self.move_wh:
            wh_indices = [
                i for i, t in enumerate(final_tokens)
                if t.lower() in _WH_WORDS
            ]
            if wh_indices:
                wh_idx = wh_indices[0]
                wh_token = final_tokens.pop(wh_idx)
                final_tokens.append(wh_token)
                notes.append("WH-question: moved wh-word to end")

        # Add question markers
        if question_type == "yn":
            final_tokens.append("Y/N")
            notes.append("Y/N question marker added")
        elif question_type == "wh":
            final_tokens.append("?")

        gloss = " ".join(final_tokens)
        return GlossResult(source=text, gloss=gloss, tokens=final_tokens, notes=notes)

    def convert_batch(self, texts: list[str]) -> list[GlossResult]:
        """Convert multiple sentences."""
        return [self.convert(t) for t in texts]


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_text(results: list[GlossResult]) -> str:
    """Format results as plain text pairs."""
    lines: list[str] = []
    for r in results:
        lines.append(f"EN:  {r.source}")
        lines.append(f"ASL: {r.gloss}")
        if r.notes:
            for note in r.notes:
                lines.append(f"     [{note}]")
        lines.append("")
    return "\n".join(lines)


def format_json(results: list[GlossResult]) -> str:
    """Format results as JSON."""
    return json.dumps(
        [
            {
                "source": r.source,
                "gloss": r.gloss,
                "tokens": r.tokens,
                "notes": r.notes,
            }
            for r in results
        ],
        indent=2,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert English text to ASL gloss (pre-processing aid for interpreters).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("text", nargs="?", help="English sentence(s) to convert")
    group.add_argument("--file", type=Path, help="File of sentences (one per line)")
    parser.add_argument(
        "--format", dest="output_format", choices=["text", "json"], default="text",
    )
    parser.add_argument(
        "--keep-articles", action="store_true",
        help="Do not remove articles (a, an, the)",
    )
    parser.add_argument(
        "--keep-copula", action="store_true",
        help="Do not remove copula verbs",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    converter = GlossConverter(
        drop_articles=not args.keep_articles,
        drop_copula=not args.keep_copula,
    )

    if args.file:
        sentences = [
            line.strip()
            for line in args.file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    else:
        sentences = [args.text]

    results = converter.convert_batch(sentences)

    if args.output_format == "json":
        print(format_json(results))
    else:
        print(format_text(results), end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
