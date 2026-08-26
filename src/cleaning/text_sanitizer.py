"""
Text sanitization for descriptions pulled from HTML pages, RSS feeds, and
API responses that sometimes embed markup, badges, or excessive whitespace.
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

_BADGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]*\)")  # markdown image badges
_MULTI_SPACE = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_MD_LINK = re.compile(r"\[([^\]]+)\]\((?:[^)]+)\)")  # [text](url) -> text


def strip_html(raw: str) -> str:
    """Remove HTML tags, decode entities, collapse whitespace."""
    if not raw:
        return ""
    soup = BeautifulSoup(raw, "html.parser")
    text = soup.get_text(separator=" ")
    text = html.unescape(text)
    return text


def clean_markdown_noise(raw: str) -> str:
    """Strip markdown badges/shields and convert links to plain text."""
    if not raw:
        return ""
    text = _BADGE_PATTERN.sub("", raw)
    text = _MD_LINK.sub(r"\1", text)
    return text


def normalize_whitespace(raw: str) -> str:
    if not raw:
        return ""
    text = _MULTI_SPACE.sub(" ", raw)
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def sanitize_description(raw: str, max_length: int = 600) -> str:
    """
    Full sanitization pipeline for a description field:
    HTML strip -> markdown noise strip -> whitespace normalize -> truncate.
    """
    if not raw:
        return ""
    text = strip_html(raw)
    text = clean_markdown_noise(text)
    text = normalize_whitespace(text)
    if len(text) > max_length:
        text = text[:max_length].rsplit(" ", 1)[0].rstrip(",.;: ") + "…"
    return text
