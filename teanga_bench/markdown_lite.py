"""A small Markdown-to-HTML converter for the methodology page.

Handles headings, paragraphs, bullet and numbered lists, pipe tables, fenced
code, block quotes, rules, inline code, links, bold and italic. Raw HTML in the
source is escaped, never passed through. Relative links are resolved against a
base URL so they still work on the static site.
"""

from __future__ import annotations

import posixpath
import re
from html import escape

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
_AUTOLINK = re.compile(r"&lt;(https?://[^\s&]+)&gt;")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])|(?<![\w_])_(?!\s)(.+?)(?<!\s)_(?![\w_])")
_SAFE_SCHEMES = ("http://", "https://", "mailto:")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


class _Links:
    def __init__(self, base_url: str | None, base_dir: str):
        self.base_url = base_url
        self.base_dir = base_dir

    def resolve(self, url: str) -> str | None:
        if url.startswith("#") or url.startswith(_SAFE_SCHEMES):
            return url
        if ":" in url.split("/", 1)[0]:
            return None  # javascript:, data: and other schemes are dropped
        if self.base_url is None:
            return url
        path, _, fragment = url.partition("#")
        joined = posixpath.normpath(posixpath.join(self.base_dir, path)).lstrip("/")
        if joined.startswith(".."):
            return None
        return f"{self.base_url}/{joined}" + (f"#{fragment}" if fragment else "")


def _inline(text: str, links: _Links) -> str:
    """Escape the text, then apply inline Markdown. Code spans are left literal."""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if len(part) >= 2 and part.startswith("`") and part.endswith("`"):
            out.append(f"<code>{escape(part[1:-1])}</code>")
            continue
        chunk = escape(part, quote=False)

        def link(match: re.Match) -> str:
            href = links.resolve(match.group(2).replace("&amp;", "&"))
            label = match.group(1)
            if href is None:
                return label
            return f'<a href="{escape(href)}">{label}</a>'

        chunk = _LINK.sub(link, chunk)
        chunk = _AUTOLINK.sub(lambda m: f'<a href="{escape(m.group(1))}">{m.group(1)}</a>', chunk)
        chunk = _BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", chunk)
        chunk = _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", chunk)
        out.append(chunk)
    return "".join(out)


def _cells(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|") and not line.endswith("\\|"):
        line = line[:-1]
    cells = re.split(r"(?<!\\)\|", line)
    return [cell.strip().replace("\\|", "|") for cell in cells]


def markdown_to_html(
    text: str,
    *,
    heading_offset: int = 0,
    base_url: str | None = None,
    base_dir: str = "",
) -> str:
    """Convert Markdown to HTML. ``heading_offset`` shifts heading levels down
    (1 turns ``#`` into ``<h2>``). ``base_url`` plus ``base_dir`` resolve relative
    links, for example to the repository on GitHub."""
    links = _Links(base_url, base_dir)
    lines = text.replace("\r\n", "\n").split("\n")
    html: list[str] = []
    used_ids: set[str] = set()
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            html.append(f"<p>{_inline(' '.join(line.strip() for line in paragraph), links)}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_paragraph()
            index += 1
            continue
        fence = _FENCE.match(line)
        if fence:
            flush_paragraph()
            marker = fence.group(1)
            body = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(marker):
                body.append(lines[index])
                index += 1
            index += 1
            html.append(f"<pre><code>{escape(chr(10).join(body))}</code></pre>")
            continue
        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            level = min(6, len(heading.group(1)) + heading_offset)
            title = heading.group(2)
            anchor = slugify(title)
            base, n = anchor, 2
            while anchor in used_ids:
                anchor = f"{base}-{n}"
                n += 1
            used_ids.add(anchor)
            html.append(f'<h{level} id="{anchor}">{_inline(title, links)}</h{level}>')
            index += 1
            continue
        if _HR.match(line) and not paragraph:
            html.append("<hr>")
            index += 1
            continue
        if "|" in stripped and index + 1 < len(lines) and _TABLE_RULE.match(lines[index + 1]):
            flush_paragraph()
            header = _cells(line)
            index += 2
            rows = []
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(_cells(lines[index]))
                index += 1
            head = "".join(f'<th scope="col">{_inline(cell, links)}</th>' for cell in header)
            body_rows = []
            for row in rows:
                row = (row + [""] * len(header))[: len(header)]
                body_rows.append("<tr>" + "".join(f"<td>{_inline(cell, links)}</td>" for cell in row) + "</tr>")
            html.append(
                '<div class="table-scroll"><table><thead><tr>'
                + head
                + "</tr></thead><tbody>"
                + "".join(body_rows)
                + "</tbody></table></div>"
            )
            continue
        if stripped.startswith(">"):
            flush_paragraph()
            quoted = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quoted.append(lines[index].strip()[1:].lstrip())
                index += 1
            inner = markdown_to_html("\n".join(quoted), heading_offset=heading_offset, base_url=base_url, base_dir=base_dir)
            html.append(f"<blockquote>{inner}</blockquote>")
            continue
        bullet, numbered = _BULLET.match(line), _NUMBERED.match(line)
        if (bullet or numbered) and not paragraph:
            pattern = _BULLET if bullet else _NUMBERED
            tag = "ul" if bullet else "ol"
            items: list[str] = []
            while index < len(lines):
                current = lines[index]
                match = pattern.match(current)
                if match:
                    items.append(match.group(1).strip())
                elif current.strip() and current.startswith((" ", "\t")) and items:
                    items[-1] += " " + current.strip()
                else:
                    break
                index += 1
            html.append(f"<{tag}>" + "".join(f"<li>{_inline(item, links)}</li>" for item in items) + f"</{tag}>")
            continue
        paragraph.append(line)
        index += 1
    flush_paragraph()
    return "\n".join(html)
