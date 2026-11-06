"""Turn SAOS ``textContent`` HTML into plain text and split it into parts.

Judgment texts arrive as simple HTML (``<p>``, ``<strong>``, ``<span
class="anon-block">`` around anonymised names, ``<!-- -->`` comments). The
operative part (*sentencja*) comes first; written reasons (*uzasadnienie*)
follow under a heading that is written either as ``UZASADNIENIE`` or with
spaced letters, ``U Z A S A D N I E N I E``.
"""

from __future__ import annotations

import html as html_lib
import re

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_BLOCK_TAG = re.compile(r"</?(?:p|div|br|h[1-6]|li|ul|ol|tr|table|blockquote)\b[^>]*>", re.I)
_ANY_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v ]+")

# A line that ends with the heading, allowing a short prefix such as a case
# number or a judge's name ("Sygn. akt II AKa 147/05 UZASADNIENIE") and
# trailing punctuation ("Uzasadnienie:"). Lower-case "uzasadnienie" is never a
# heading, it is an ordinary word in the operative part.
_REASONS_HEADING = re.compile(
    r"(?m)^[^\n]{0,60}?\b(?:U\s?Z\s?A\s?S\s?A\s?D\s?N\s?I\s?E\s?N\s?I\s?E|Uzasadnienie)\b"
    r"[^\n]{0,5}$"
)


def html_to_text(html: str) -> str:
    """Strip tags, decode entities and normalise whitespace; block tags become newlines."""
    text = _COMMENT.sub("", html)
    text = _BLOCK_TAG.sub("\n", text)
    text = _ANY_TAG.sub("", text)
    text = html_lib.unescape(text)
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    out: list[str] = []
    for line in lines:
        if line:
            out.append(line)
        elif out and out[-1]:
            out.append("")
    return "\n".join(out).strip()


def split_operative_reasons(text: str) -> tuple[str, str]:
    """Split plain text at the reasons heading. Returns ``(operative, reasons)``.

    Without a heading everything is treated as the operative part.
    """
    match = _REASONS_HEADING.search(text)
    if not match:
        return text, ""
    return text[: match.start()].strip(), text[match.end() :].strip()
