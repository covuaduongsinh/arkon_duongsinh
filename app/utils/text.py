import json
import re
import unicodedata
from typing import Any


def strip_code_fence(raw: str) -> str:
    """
    Remove a surrounding ```json ... ``` (or plain ``` ... ```) fence from an
    LLM response. Unlike `str.strip("```json")`, which strips any of those
    characters and can corrupt valid JSON, this matches the fence as a substring.
    """
    s = raw.strip()
    # Leading fence
    s = re.sub(r"^```(?:json|JSON)?\s*\n?", "", s)
    # Trailing fence
    s = re.sub(r"\n?```\s*$", "", s)
    return s.strip()


def parse_json_loose(raw: str) -> Any:
    """
    Parse a JSON value from an LLM response that may be wrapped in a code fence
    or have trailing prose. Falls back to truncating at the last `}` or `]`.
    """
    cleaned = strip_code_fence(raw)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        last = max(cleaned.rfind("}"), cleaned.rfind("]"))
        if last != -1:
            return json.loads(cleaned[: last + 1])
        raise


def slugify(text: str, max_len: int | None = None) -> str:
    """
    Convert text to a URL-friendly slug.
    Supports Vietnamese characters by removing diacritics.

    `đ`/`Đ` are mapped to `d` first — NFKD does not decompose the stroke, so
    without this they'd be dropped by the ascii filter ("đường" → "uong").
    `max_len` truncates the result (then trims a dangling hyphen).
    """
    if not text:
        return ""

    # Map đ/Đ → d, then lowercase.
    text = text.replace("đ", "d").replace("Đ", "D").lower()

    # Remove the remaining Vietnamese diacritics.
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')

    # Replace non-alphanumeric characters with hyphens; collapse and trim.
    text = re.sub(r'[^a-z0-9]+', '-', text).strip('-')

    if max_len:
        text = text[:max_len].strip('-')

    return text
