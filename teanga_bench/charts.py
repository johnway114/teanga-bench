"""SVG charts drawn with plain string building. No plotting library.

Every chart has an explicit light background and dark text, so it reads on a
light or dark page.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from xml.sax.saxutils import escape

BACKGROUND = "#ffffff"
TEXT = "#1a1a1a"
MUTED = "#555555"
GRID = "#d9d9d9"
BAR = "#4c78a8"
WHISKER = "#1a1a1a"
POINT = "#d1495b"
FONT = "font-family=\"Helvetica, Arial, sans-serif\""


@dataclass(frozen=True)
class Bar:
    label: str
    value: float  # 0..1
    low: float | None = None
    high: float | None = None


@dataclass(frozen=True)
class Point:
    label: str
    x: float  # cost in USD
    y: float  # score 0..1


def _svg(width: int, height: int, body: list[str]) -> str:
    head = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
    )
    background = f'<rect x="0" y="0" width="{width}" height="{height}" fill="{BACKGROUND}"/>'
    return "\n".join([head, background, *body, "</svg>", ""])


def _text(x: float, y: float, text: str, size: int = 12, anchor: str = "start", fill: str = TEXT, weight: str = "normal") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{fill}" font-weight="{weight}" {FONT}>{escape(text)}</text>'
    )


def _title(title: str, subtitle: str | None, width: int) -> list[str]:
    parts = [_text(20, 28, title, size=16, weight="bold")]
    if subtitle:
        parts.append(_text(20, 46, subtitle, size=11, fill=MUTED))
    return parts


def _empty(title: str, message: str) -> str:
    body = _title(title, None, 640) + [_text(20, 80, message, size=13, fill=MUTED)]
    return _svg(640, 110, body)


def _clip_label(label: str, limit: int = 38) -> str:
    return label if len(label) <= limit else label[: limit - 1] + "…"


def bar_chart(title: str, bars: list[Bar], subtitle: str | None = None) -> str:
    """Horizontal bars of a 0..1 score, with 95% interval whiskers."""
    if not bars:
        return _empty(title, "No complete runs yet.")
    bars = sorted(bars, key=lambda bar: (-bar.value, bar.label))
    left, plot_w, right, top, row = 270, 440, 70, 64, 30
    width = left + plot_w + right
    height = top + row * len(bars) + 40
    body = _title(title, subtitle, width)

    def x_of(value: float) -> float:
        return left + max(0.0, min(1.0, value)) * plot_w

    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        x = x_of(tick)
        body.append(f'<line x1="{x:.1f}" y1="{top - 6}" x2="{x:.1f}" y2="{top + row * len(bars)}" stroke="{GRID}" stroke-width="1"/>')
        body.append(_text(x, top + row * len(bars) + 18, f"{int(tick * 100)}%", size=11, anchor="middle", fill=MUTED))
    for index, bar in enumerate(bars):
        y = top + index * row
        mid = y + row / 2
        body.append(_text(left - 8, mid + 4, _clip_label(bar.label), size=12, anchor="end"))
        body.append(
            f'<rect x="{left}" y="{y + 5}" width="{x_of(bar.value) - left:.1f}" height="{row - 10}" fill="{BAR}"/>'
        )
        if bar.low is not None and bar.high is not None:
            lo, hi = x_of(bar.low), x_of(bar.high)
            body.append(f'<line x1="{lo:.1f}" y1="{mid:.1f}" x2="{hi:.1f}" y2="{mid:.1f}" stroke="{WHISKER}" stroke-width="1.5"/>')
            for cap in (lo, hi):
                body.append(f'<line x1="{cap:.1f}" y1="{mid - 5:.1f}" x2="{cap:.1f}" y2="{mid + 5:.1f}" stroke="{WHISKER}" stroke-width="1.5"/>')
        label_x = x_of(bar.high if bar.high is not None else bar.value) + 6
        body.append(_text(label_x, mid + 4, f"{bar.value * 100:.1f}%", size=11))
    return _svg(width, height, body)


def _nice_max(value: float) -> float:
    """Round an axis maximum up to 1, 2, 2.5, 5 or 10 times a power of ten."""
    if value <= 0:
        return 1.0
    base = 10.0 ** math.floor(math.log10(value))
    for step in (1, 2, 2.5, 5, 10):
        if value <= step * base:
            return step * base
    return 10 * base


def scatter_chart(title: str, points: list[Point], subtitle: str | None = None) -> str:
    """Overall score (y, 0..100%) against run cost in USD (x)."""
    if not points:
        return _empty(title, "No complete runs yet.")
    left, plot_w, right, top, plot_h = 70, 520, 220, 64, 300
    width = left + plot_w + right
    height = top + plot_h + 60
    x_max = _nice_max(max(point.x for point in points) * 1.05)
    body = _title(title, subtitle, width)

    def x_of(value: float) -> float:
        return left + min(value / x_max, 1.0) * plot_w

    def y_of(value: float) -> float:
        return top + plot_h - max(0.0, min(1.0, value)) * plot_h

    for tick in (0, 0.25, 0.5, 0.75, 1.0):
        y = y_of(tick)
        body.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        body.append(_text(left - 8, y + 4, f"{int(tick * 100)}%", size=11, anchor="end", fill=MUTED))
    for i in range(5):
        value = x_max * i / 4
        x = x_of(value)
        body.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" stroke="{GRID}" stroke-width="1"/>')
        body.append(_text(x, top + plot_h + 18, f"${value:g}", size=11, anchor="middle", fill=MUTED))
    body.append(_text(left + plot_w / 2, top + plot_h + 42, "Run cost (USD, candidate plus judges)", size=12, anchor="middle"))
    body.append(_text(16, top + plot_h / 2, "Overall score", size=12, anchor="middle").replace(
        "<text ", f'<text transform="rotate(-90 16 {top + plot_h / 2:.1f})" ', 1))
    for point in sorted(points, key=lambda p: (p.x, p.label)):
        cx, cy = x_of(point.x), y_of(point.y)
        body.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="5" fill="{POINT}" stroke="{TEXT}" stroke-width="0.5"/>')
        body.append(_text(cx + 8, cy + 4, _clip_label(point.label, 34), size=11))
    return _svg(width, height, body)
