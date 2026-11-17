"""Deterministic 1200x630 PNG social preview cards for Teanga Bench suites.

Social platforms (X/Twitter, LinkedIn, Discord) require raster PNG or JPEG
cards for ``og:image`` and ``twitter:image`` and reject SVG. This module builds
a suite-themed SVG card from the ranked leaderboard data and rasterises it
deterministically via ``rsvg-convert`` (or ``magick`` / pure-Python PNG
fallback when raster CLI tools are unavailable).
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import textwrap
import zlib
from dataclasses import dataclass
from html import escape
from typing import Sequence

CARD_WIDTH = 1200
CARD_HEIGHT = 630
MAX_ROWS = 5
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FONT_SANS = "Helvetica Neue, Helvetica, Arial, sans-serif"

_PALETTES = {
    "blas": {
        "accent": "#ec9a36",
        "accent_soft": "#fdf3e6",
        "accent_ink": "#8a5a1e",
        "accent_on": "#1a1917",
        "accent_mid": "#e5a856",
    },
    "tonada": {
        "accent": "#8a3b78",
        "accent_soft": "#f6ecf3",
        "accent_ink": "#6e2f60",
        "accent_on": "#ffffff",
        "accent_mid": "#a95c97",
    },
}


@dataclass(frozen=True)
class CardRow:
    """One ranked model row shown on the social preview card."""

    rank: int
    display: str
    provider: str
    score: float


@dataclass(frozen=True)
class CardSpec:
    """All inputs needed to render one suite's 1200x630 social card."""

    suite_key: str
    suite_name: str
    headline: str
    description: str
    domain: str
    n_tests: int
    total_ranked: int
    rows: tuple[CardRow, ...]
    updated_label: str | None = None


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _hex_rgb(code: str) -> tuple[int, int, int]:
    raw = code.lstrip("#")
    return int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16)


def build_card_svg(spec: CardSpec) -> str:
    """Return a deterministic 1200x630 SVG for ``spec``."""
    palette = _PALETTES.get(spec.suite_key, _PALETTES["blas"])
    accent = palette["accent"]
    accent_soft = palette["accent_soft"]
    accent_ink = palette["accent_ink"]
    accent_on = palette["accent_on"]
    accent_mid = palette["accent_mid"]

    eyebrow = f"TEANGA BENCH · {spec.suite_name.upper()}"
    eyebrow_w = max(210, int(len(eyebrow) * 9.5 + 38))

    headline_lines = textwrap.wrap(spec.headline, width=23)[:3]
    desc_text = f"{spec.description} · {spec.n_tests} tests"
    desc_lines = textwrap.wrap(desc_text, width=38)[:3]

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CARD_WIDTH}" height="{CARD_HEIGHT}" '
        f'viewBox="0 0 {CARD_WIDTH} {CARD_HEIGHT}">',
        '<rect width="1200" height="630" fill="#f8f7f5"/>',
        f'<rect width="1200" height="10" fill="{accent}"/>',
        # Left column: suite identity & summary
        f'<rect x="56" y="54" width="{eyebrow_w}" height="34" rx="17" fill="{accent_soft}"/>',
        f'<text x="{56 + eyebrow_w / 2:.1f}" y="76" text-anchor="middle" font-family="{FONT_SANS}" '
        f'font-size="14" font-weight="700" letter-spacing="0.8" fill="{accent_ink}">{escape(eyebrow)}</text>',
    ]

    hy = 148
    for line in headline_lines:
        parts.append(
            f'<text x="56" y="{hy}" font-family="{FONT_SANS}" font-size="40" '
            f'font-weight="700" fill="#1a1917">{escape(line)}</text>'
        )
        hy += 50

    dy = hy + 18
    for line in desc_lines:
        parts.append(
            f'<text x="56" y="{dy}" font-family="{FONT_SANS}" font-size="21" '
            f'font-weight="400" fill="#3d3b38">{escape(line)}</text>'
        )
        dy += 31

    # Bottom-left metadata & domain
    parts.append('<line x1="56" y1="504" x2="532" y2="504" stroke="#dcd9d2" stroke-width="1.5"/>')
    parts.append(
        f'<text x="56" y="540" font-family="{FONT_SANS}" font-size="22" font-weight="700" '
        f'fill="{accent_ink}">{escape(spec.domain)}</text>'
    )
    if spec.total_ranked:
        noun = "model" if spec.total_ranked == 1 else "models"
        meta = f"{spec.total_ranked} {noun} ranked"
        if spec.updated_label:
            meta += f" · {spec.updated_label}"
        meta += " · Apache-2.0"
    else:
        meta = "Open benchmark · Apache-2.0"
    parts.append(
        f'<text x="56" y="570" font-family="{FONT_SANS}" font-size="16" font-weight="400" '
        f'fill="#56544f">{escape(meta)}</text>'
    )

    # Right column: leaderboard card
    parts.append(
        '<rect x="572" y="52" width="572" height="526" rx="18" fill="#ffffff" '
        'stroke="#dcd9d2" stroke-width="1.5"/>'
    )
    parts.append(
        f'<text x="604" y="96" font-family="{FONT_SANS}" font-size="21" font-weight="700" '
        f'fill="#1a1917">Leaderboard</text>'
    )
    parts.append(
        f'<text x="1112" y="96" text-anchor="end" font-family="{FONT_SANS}" font-size="15" '
        f'font-weight="500" fill="#56544f">Overall score</text>'
    )
    parts.append('<line x1="604" y1="116" x2="1112" y2="116" stroke="#ebe9e4" stroke-width="1.5"/>')

    rows = spec.rows[:MAX_ROWS]
    if rows:
        bar_x = 604
        bar_w = 508
        for idx, row in enumerate(rows):
            ry = 148 + idx * 84
            is_first = row.rank == 1
            badge_fill = accent if is_first else "#ecebe6"
            badge_ink = accent_on if is_first else "#3d3b38"
            bar_fill = accent if is_first else accent_mid
            clamped = max(0.0, min(1.0, row.score))
            fill_w = max(8.0, round(bar_w * clamped, 1))
            score_txt = f"{row.score * 100:.1f}%"
            name_txt = _truncate(row.display, 24)
            provider_txt = f"· {row.provider}" if row.provider else ""

            parts.append(f'<circle cx="620" cy="{ry + 6}" r="14" fill="{badge_fill}"/>')
            parts.append(
                f'<text x="620" y="{ry + 11}" text-anchor="middle" font-family="{FONT_SANS}" '
                f'font-size="14" font-weight="700" fill="{badge_ink}">{row.rank}</text>'
            )
            parts.append(
                f'<text x="646" y="{ry + 12}" font-family="{FONT_SANS}" font-size="18" '
                f'font-weight="700" fill="#1a1917">{escape(name_txt)}'
                + (
                    f'<tspan dx="6" font-size="14" font-weight="400" fill="#56544f">{escape(provider_txt)}</tspan>'
                    if provider_txt
                    else ""
                )
                + "</text>"
            )
            parts.append(
                f'<text x="1112" y="{ry + 12}" text-anchor="end" font-family="{FONT_SANS}" '
                f'font-size="19" font-weight="700" fill="#1a1917">{escape(score_txt)}</text>'
            )
            parts.append(
                f'<rect x="{bar_x}" y="{ry + 28}" width="{bar_w}" height="14" rx="7" fill="#ecebe6"/>'
            )
            parts.append(
                f'<rect x="{bar_x}" y="{ry + 28}" width="{fill_w}" height="14" rx="7" fill="{bar_fill}"/>'
            )
    else:
        parts.append(
            f'<text x="858" y="310" text-anchor="middle" font-family="{FONT_SANS}" '
            f'font-size="20" font-weight="600" fill="#3d3b38">Results appear after the first run</text>'
        )
        parts.append(
            f'<text x="858" y="344" text-anchor="middle" font-family="{FONT_SANS}" '
            f'font-size="16" fill="#56544f">{spec.n_tests} tests · open source evaluation</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)


def _png_chunk(tag: bytes, payload: bytes) -> bytes:
    crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
    return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)


def _fallback_png(spec: CardSpec) -> bytes:
    """Pure-Python deterministic 1200x630 RGB PNG fallback if no SVG rasteriser exists."""
    palette = _PALETTES.get(spec.suite_key, _PALETTES["blas"])
    bg = _hex_rgb("#f8f7f5")
    accent = _hex_rgb(palette["accent"])
    accent_mid = _hex_rgb(palette["accent_mid"])
    paper = _hex_rgb("#ffffff")
    rule = _hex_rgb("#dcd9d2")
    track = _hex_rgb("#ecebe6")
    ink = _hex_rgb("#1a1917")

    bg_row = bytes(bg) * CARD_WIDTH
    rows = [bytearray(bg_row) for _ in range(CARD_HEIGHT)]

    def fill_rect(x0: int, y0: int, w: int, h: int, color: tuple[int, int, int]) -> None:
        r, g, b = color
        x_start = max(0, x0)
        x_end = min(CARD_WIDTH, x0 + w)
        if x_start >= x_end:
            return
        span = bytes((r, g, b)) * (x_end - x_start)
        s0, s1 = x_start * 3, x_end * 3
        for y in range(max(0, y0), min(CARD_HEIGHT, y0 + h)):
            rows[y][s0:s1] = span

    fill_rect(0, 0, CARD_WIDTH, 10, accent)
    fill_rect(56, 70, 240, 26, accent)
    fill_rect(56, 130, 420, 18, ink)
    fill_rect(56, 166, 360, 18, ink)
    fill_rect(572, 52, 572, 526, rule)
    fill_rect(574, 54, 568, 522, paper)
    for idx, row in enumerate(spec.rows[:MAX_ROWS]):
        ry = 176 + idx * 84
        fill_rect(604, ry, 508, 16, track)
        fill_w = max(8, int(round(508 * max(0.0, min(1.0, row.score)))))
        fill_rect(604, ry, fill_w, 16, accent if row.rank == 1 else accent_mid)

    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    ihdr = struct.pack(">IIBBBBB", CARD_WIDTH, CARD_HEIGHT, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw, level=6)
    return PNG_SIGNATURE + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if not data.startswith(PNG_SIGNATURE) or len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])


def render_card_png(spec: CardSpec) -> bytes:
    """Render ``spec`` to deterministic 1200x630 PNG bytes."""
    svg = build_card_svg(spec).encode("utf-8")

    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        proc = subprocess.run(
            [rsvg, "-w", str(CARD_WIDTH), "-h", str(CARD_HEIGHT), "-f", "png"],
            input=svg,
            capture_output=True,
        )
        if proc.returncode == 0 and _png_dimensions(proc.stdout) == (CARD_WIDTH, CARD_HEIGHT):
            return proc.stdout

    magick = shutil.which("magick")
    if magick:
        proc = subprocess.run(
            [
                magick,
                "svg:-",
                "-resize",
                f"{CARD_WIDTH}x{CARD_HEIGHT}!",
                "-strip",
                "+set",
                "date:create",
                "+set",
                "date:modify",
                "png:-",
            ],
            input=svg,
            capture_output=True,
        )
        if proc.returncode == 0 and _png_dimensions(proc.stdout) == (CARD_WIDTH, CARD_HEIGHT):
            return proc.stdout

    return _fallback_png(spec)


def card_rows_from_entries(entries: Sequence[object]) -> tuple[CardRow, ...]:
    """Extract up to ``MAX_ROWS`` ranked ``CardRow`` objects from ``site.Entry`` items."""
    out: list[CardRow] = []
    for entry in entries:
        ranked = getattr(entry, "ranked", False)
        rank = getattr(entry, "rank", None)
        score = getattr(entry, "score", None)
        if not ranked or rank is None or score is None:
            continue
        out.append(
            CardRow(
                rank=int(rank),
                display=str(getattr(entry, "display", "")),
                provider=str(getattr(entry, "provider", "")),
                score=float(score),
            )
        )
        if len(out) >= MAX_ROWS:
            break
    return tuple(out)
