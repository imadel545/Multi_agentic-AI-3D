"""Shared text normalization for deterministic and lexical retrieval paths."""

from __future__ import annotations

import re
import unicodedata

_WORD_PATTERN = re.compile(r"[^\W_]+", flags=re.UNICODE)


def normalized_tokens(text: str) -> list[str]:
    """Return accent-insensitive Unicode word tokens without losing non-ASCII scripts."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    accent_free = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _WORD_PATTERN.findall(accent_free)
