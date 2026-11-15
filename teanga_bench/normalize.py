"""Answer normalization for rule scorers.

Normalization is deliberately strict: case, apostrophe glyphs, and outer
whitespace do not matter, and a single trailing period is ignored. Extra words
are not stripped, so a paraphrase does not match a gold phrase.
"""

from __future__ import annotations

import re
import unicodedata

_APOSTROPHES = str.maketrans({
    "\u2019": "'",
    "\u2018": "'",
    "\u02bc": "'",
    "`": "'",
    "\u00b4": "'",
})


def normalize_text(text: str) -> str:
    """Normalize a phrase, span, or sentence for comparison."""
    text = unicodedata.normalize("NFC", text or "")
    text = text.translate(_APOSTROPHES)
    text = text.strip()
    text = text.strip("\"'`*_")
    text = re.sub(r"\s+", " ", text)
    text = text.rstrip(" .")
    return text.casefold()


def normalize_answer(completion: str) -> str:
    """Pull the ANSWER line, or else the last non-empty line, then normalize."""
    text = unicodedata.normalize("NFC", completion or "")
    text = text.translate(_APOSTROPHES)
    match = re.search(r"(?im)^\s*answer\s*:\s*(.+?)\s*$", text)
    if match:
        chosen = match.group(1)
    else:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        chosen = lines[-1] if lines else ""
    return normalize_text(chosen)
