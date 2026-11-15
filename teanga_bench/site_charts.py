"""Inline SVG and HTML charts for the research site.

Colours come from the page stylesheet through class names and CSS variables,
so one chart reads in either suite's accent and in the light or dark theme.
Every chart carries text a screen reader can use, and every number is also
printed as text beside the graphic.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape


@dataclass(frozen=True)
class BarRow:
    label_html: str  # already escaped HTML, may hold a link
    label_text: str  # plain text for aria labels
    score: float
    ci95: list[float] | None
    note_html: str = ""


@dataclass(frozen=True)
class ScatterPoint:
    number: int  # the leaderboard rank, drawn inside the marker
    label: str
    cost: float
    score: float
    ci95: list[float] | None


def pct(value: float | None, digits: int = 1) -> str:
    return "n/a" if value is None else f"{value * 100:.{digits}f}%"


def interval_words(ci: list[float] | None) -> str:
    return "no range" if not ci else f"{ci[0] * 100:.1f}% to {ci[1] * 100:.1f}%"


def interval_short(ci: list[float] | None) -> str:
    return "n/a" if not ci else f"{ci[0] * 100:.1f}–{ci[1] * 100:.1f}%"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def interval_bar(score: float | None, ci: list[float] | None, label: str, *, decorative: bool = False) -> str:
    """A 0..100% track with the score as a bar and the 95% range as a whisker.

    The SVG stretches to its container (``preserveAspectRatio="none"``); lines
    keep their width through ``vector-effect``. ``decorative`` hides the bar
    from screen readers where the same numbers are printed next to it.
    """
    if score is None:
        return '<span class="muted">n/a</span>'
    if decorative:
        role = 'aria-hidden="true"'
    else:
        role = f'role="img" aria-label="{escape(f"{label}: {pct(score)}, 95% range {interval_words(ci)}")}"'
    parts = [
        f'<svg class="ibar" viewBox="0 0 100 12" preserveAspectRatio="none" {role} focusable="false">',
        '<rect class="ibar-track" x="0" y="2" width="100" height="8"/>',
    ]
    for tick in (25, 50, 75):
        parts.append(f'<line class="ibar-grid" x1="{tick}" y1="2" x2="{tick}" y2="10" vector-effect="non-scaling-stroke"/>')
    parts.append(f'<rect class="ibar-fill" x="0" y="2" width="{_clamp(score) * 100:.2f}" height="8"/>')
    if ci:
        lo, hi = _clamp(ci[0]) * 100, _clamp(ci[1]) * 100
        parts.append(f'<line class="ibar-whisker" x1="{lo:.2f}" y1="6" x2="{hi:.2f}" y2="6" vector-effect="non-scaling-stroke"/>')
        for x in (lo, hi):
            parts.append(f'<line class="ibar-whisker" x1="{x:.2f}" y1="3.5" x2="{x:.2f}" y2="8.5" vector-effect="non-scaling-stroke"/>')
    parts.append("</svg>")
    return "".join(parts)


def _axis() -> str:
    ticks = "".join(
        f'<span style="left:{tick}%">{tick}%</span>' for tick in (0, 25, 50, 75, 100)
    )
    return f'<li class="bars-axis" aria-hidden="true"><span></span><span class="axis-ticks">{ticks}</span><span></span></li>'


def ranked_bars(rows: list[BarRow], caption_html: str, *, sort: bool = True) -> str:
    """Horizontal bars, highest first unless ``sort`` is off. Text holds every number."""
    if not rows:
        return f'<p class="empty-note">{caption_html} No complete runs yet.</p>'
    if sort:
        rows = sorted(rows, key=lambda row: (-row.score, row.label_text))
    items = []
    for row in rows:
        items.append(
            "<li>"
            f'<span class="bar-label">{row.label_html}{row.note_html}</span>'
            f'<span class="bar-track">{interval_bar(row.score, row.ci95, row.label_text)}</span>'
            f'<span class="bar-value" aria-hidden="true"><strong>{pct(row.score)}</strong>'
            + (f' <span class="ci">{interval_short(row.ci95)}</span>' if row.ci95 else "")
            + "</span></li>"
        )
    caption = f"<figcaption>{caption_html}</figcaption>" if caption_html else ""
    return f'<figure class="chart">{caption}<ol class="bars">{"".join(items)}{_axis()}</ol></figure>'


def mini_bar(score: float | None) -> str:
    """A small plain bar for compact lists; the number is printed beside it."""
    if score is None:
        return ""
    return f'<span class="mini" aria-hidden="true"><span style="width:{_clamp(score) * 100:.1f}%"></span></span>'


def _ticks_linear(maximum: float) -> list[float]:
    if maximum <= 0:
        return [0.0, 1.0]
    base = 10.0 ** math.floor(math.log10(maximum))
    for step in (1, 2, 2.5, 5, 10):
        top = step * base
        if maximum <= top:
            break
    return [top * i / 4 for i in range(5)]


def _ticks_log(low: float, high: float) -> list[float]:
    ticks = []
    exponent = math.floor(math.log10(low))
    while True:
        for step in (1, 2, 5):
            value = step * 10.0**exponent
            if value > high * 1.0001:
                return ticks
            if value >= low * 0.9999:
                ticks.append(value)
        exponent += 1


def money(value: float | None) -> str:
    """US dollars: cents from $0.01 up, three significant figures below."""
    if value is None:
        return "n/a"
    if value == 0:
        return "$0"
    if value >= 0.01:
        return f"${value:,.2f}"
    return f"${value:.3g}" if value >= 0.0001 else f"${value:.2e}"


def _money_ticks(ticks: list[float]) -> list[str]:
    """Tick labels in one style: whole dollars when every tick is whole."""
    if all(t == int(t) for t in ticks):
        return [f"${int(t)}" for t in ticks]
    if all(t == 0 or t >= 0.01 for t in ticks):
        return ["$0" if t == 0 else f"${t:.2f}" for t in ticks]
    return ["$0" if t == 0 else f"${t:.2g}" for t in ticks]


def _score_axis(points: list[ScatterPoint]) -> tuple[float, float, float]:
    """Score axis bounds and tick step, zoomed to the data (and its intervals)."""
    lows = [p.ci95[0] if p.ci95 else p.score for p in points]
    highs = [p.ci95[1] if p.ci95 else p.score for p in points]
    lo = max(0.0, math.floor((min(lows) - 0.03) * 10) / 10)
    hi = min(1.0, math.ceil((max(highs) + 0.03) * 10) / 10)
    span = hi - lo
    step = 0.05 if span <= 0.3 else 0.1 if span <= 0.6 else 0.2 if span <= 0.8 else 0.25
    if step == 0.25:
        lo, hi = 0.0, 1.0
    elif step == 0.2:
        lo = math.floor(lo * 5) / 5
        hi = min(1.0, lo + 0.2 * math.ceil(round((hi - lo) / 0.2, 6)))
    return lo, hi, step


def scatter(points: list[ScatterPoint], chart_id: str, title: str) -> str:
    """Score (y) against cost (x). Markers carry the leaderboard rank; the
    legend beside the chart names each one. The x axis is logarithmic when
    costs span ten times or more."""
    if not points:
        return '<p class="empty-note">No complete runs yet.</p>'
    width, height = 560, 400
    left, right, top, bottom = 60, 24, 20, 66
    plot_w, plot_h = width - left - right, height - top - bottom
    costs = [p.cost for p in points]
    low, high = min(costs), max(costs)
    log_scale = low > 0 and high / low >= 10
    if log_scale:
        lo_axis = 10.0 ** math.floor(math.log10(low))
        hi_axis = 10.0 ** math.ceil(math.log10(high))
        ticks = _ticks_log(lo_axis, hi_axis)

        def x_of(value: float) -> float:
            span = math.log10(hi_axis) - math.log10(lo_axis)
            return left + (math.log10(value) - math.log10(lo_axis)) / span * plot_w
    else:
        ticks = _ticks_linear(high * 1.08)
        hi_axis = ticks[-1]

        def x_of(value: float) -> float:
            return left + (value / hi_axis) * plot_w

    y_lo, y_hi, y_step = _score_axis(points)

    def y_of(value: float) -> float:
        return top + (1 - (_clamp(value) - y_lo) / (y_hi - y_lo)) * plot_h

    title_id, desc_id = f"{chart_id}-title", f"{chart_id}-desc"
    description = "; ".join(
        f"{p.number}. {p.label}: {pct(p.score)} for {money(p.cost)}"
        for p in sorted(points, key=lambda p: p.number)
    )
    body = [
        f'<svg class="scatter" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{escape(title)}</title>',
        f'<desc id="{desc_id}">{escape(description)}</desc>',
        f'<rect class="sc-bg" x="{left}" y="{top}" width="{plot_w}" height="{plot_h}"/>',
    ]
    n_ticks = int(round((y_hi - y_lo) / y_step))
    for i in range(n_ticks + 1):
        tick = y_lo + i * y_step
        y = y_of(tick)
        body.append(f'<line class="sc-grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}"/>')
        body.append(f'<text class="sc-tick" x="{left - 8}" y="{y + 4:.1f}" text-anchor="end">{tick * 100:.0f}%</text>')
    for tick, tick_label in zip(ticks, _money_ticks(ticks)):
        x = x_of(tick)
        body.append(f'<line class="sc-grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}"/>')
        body.append(f'<text class="sc-tick" x="{x:.1f}" y="{top + plot_h + 22}" text-anchor="middle">{tick_label}</text>')
    axis_title = "Cost of one run of this suite (USD" + (", log scale)" if log_scale else ")")
    body.append(f'<text class="sc-axis" x="{left + plot_w / 2:.1f}" y="{height - 12}" text-anchor="middle">{axis_title}</text>')
    mid = top + plot_h / 2
    body.append(f'<text class="sc-axis" x="18" y="{mid:.1f}" text-anchor="middle" transform="rotate(-90 18 {mid:.1f})">Score</text>')
    # Draw low ranks last so the best model sits on top where markers overlap.
    for point in sorted(points, key=lambda p: -p.number):
        cx, cy = x_of(point.cost), y_of(point.score)
        if point.ci95:
            y1, y2 = y_of(point.ci95[1]), y_of(point.ci95[0])
            body.append(f'<line class="sc-whisker" x1="{cx:.1f}" y1="{y1:.1f}" x2="{cx:.1f}" y2="{y2:.1f}"/>')
            for y in (y1, y2):
                body.append(f'<line class="sc-whisker" x1="{cx - 5:.1f}" y1="{y:.1f}" x2="{cx + 5:.1f}" y2="{y:.1f}"/>')
        body.append(f'<circle class="sc-point" cx="{cx:.1f}" cy="{cy:.1f}" r="13"/>')
        body.append(f'<text class="sc-num" x="{cx:.1f}" y="{cy + 5:.1f}" text-anchor="middle">{point.number}</text>')
    body.append("</svg>")
    return "".join(body)


def heat_style(score: float | None) -> str:
    """How strongly a grid cell mixes the accent into the card colour. The
    stylesheet does the mixing, so the cell reads in both themes. The curve
    spreads the common 40-90% range."""
    if score is None:
        return ""
    weight = 0.04 + 0.64 * _clamp(score) ** 1.5
    return f' style="--h:{weight * 100:.0f}%"'
