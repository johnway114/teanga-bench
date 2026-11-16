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
from typing import Callable, Sequence


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


PERCENT_TICKS = tuple((tick / 100, f"{tick}%") for tick in (0, 25, 50, 75, 100))


def _axis(ticks: Sequence[tuple[float, str]] = PERCENT_TICKS) -> str:
    """The tick row under a list of bars; positions run 0..1 along the track."""
    spans = "".join(f'<span style="left:{_clamp(pos) * 100:.2f}%">{escape(label)}</span>' for pos, label in ticks)
    return f'<li class="bars-axis" aria-hidden="true"><span></span><span class="axis-ticks">{spans}</span><span></span></li>'


def ranked_bars(rows: list[BarRow], *, sort: bool = True) -> str:
    """Horizontal bars, highest first unless ``sort`` is off. Text holds every
    number. The caller wraps the list in a figure with its takeaway."""
    if not rows:
        return '<p class="empty-note">No complete runs yet.</p>'
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
    return f'<ol class="bars">{"".join(items)}{_axis()}</ol>'


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


def _ticks_log(low: float, high: float, *, most: int = 7) -> list[float]:
    """1-2-5 ticks from low to high; the 2s, then the 5s, go when there are too many to read."""
    ticks = []
    exponent = math.floor(math.log10(low))
    while exponent <= math.ceil(math.log10(high)):
        for step in (1, 2, 5):
            value = step * 10.0**exponent
            if low * 0.9999 <= value <= high * 1.0001:
                ticks.append(value)
        exponent += 1
    for keep in ((1, 5), (1,)):
        if len(ticks) <= most:
            break
        ticks = [t for t in ticks if round(t / 10.0 ** math.floor(math.log10(t) + 1e-9)) in keep]
    return ticks


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
    """Tick labels in one style: whole dollars without cents, cents from $0.01 up."""
    labels = []
    for t in ticks:
        if t == int(t):
            labels.append(f"${int(t)}")
        elif t >= 0.01:
            labels.append(f"${t:.2f}")
        else:
            labels.append(f"${t:.2g}")
    return labels


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


def scatter(points: list[ScatterPoint], chart_id: str, title: str, *, consistency: bool = False) -> str:
    """Score (y) against cost (x). Markers carry the leaderboard rank; the
    legend beside the chart names each one. The x axis is logarithmic when
    costs span ten times or more. With ``consistency``, x is a share on 0..100%."""
    if not points:
        return '<p class="empty-note">No complete runs yet.</p>'
    width, height = (420 if consistency else 560), 400
    left, right, top, bottom = 60, 24, 20, 66
    plot_w, plot_h = width - left - right, height - top - bottom
    costs = [p.cost for p in points]
    low, high = min(costs), max(costs)
    log_scale = not consistency and low > 0 and high / low >= 10
    if log_scale:
        lo_axis = 10.0 ** math.floor(math.log10(low))
        hi_axis = 10.0 ** math.ceil(math.log10(high))
        ticks = _ticks_log(lo_axis, hi_axis)

        def x_of(value: float) -> float:
            span = math.log10(hi_axis) - math.log10(lo_axis)
            return left + (math.log10(value) - math.log10(lo_axis)) / span * plot_w
    else:
        ticks = [0.0, 0.25, 0.5, 0.75, 1.0] if consistency else _ticks_linear(high * 1.08)
        hi_axis = ticks[-1]

        def x_of(value: float) -> float:
            return left + (value / hi_axis) * plot_w

    y_lo, y_hi, y_step = _score_axis(points)
    def y_of(value: float) -> float:
        return top + (1 - (_clamp(value) - y_lo) / (y_hi - y_lo)) * plot_h

    title_id, desc_id = f"{chart_id}-title", f"{chart_id}-desc"
    description = "; ".join(
        (f"{p.number}. {p.label}: {pct(p.score)}, consistency {pct(p.cost)}" if consistency
         else f"{p.number}. {p.label}: {pct(p.score)} for {money(p.cost)}")
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
    for tick, tick_label in zip(ticks, [pct(t, 0) for t in ticks] if consistency else _money_ticks(ticks)):
        x = x_of(tick)
        body.append(f'<line class="sc-grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}"/>')
        body.append(f'<text class="sc-tick" x="{x:.1f}" y="{top + plot_h + 22}" text-anchor="middle">{tick_label}</text>')
    axis_title = "Mean consistency" if consistency else "Cost of one run of this suite (USD" + (", log scale)" if log_scale else ")")
    body.append(f'<text class="sc-axis" x="{left + plot_w / 2:.1f}" y="{height - 12}" text-anchor="middle">{axis_title}</text>')
    mid = top + plot_h / 2
    body.append(f'<text class="sc-axis" x="18" y="{mid:.1f}" text-anchor="middle" transform="rotate(-90 18 {mid:.1f})">Score</text>')
    label_positions: dict[int, tuple[float, float]] = {}
    if consistency:
        # Keep every rank readable in tight clusters without moving its data
        # point. Displaced labels get a leader line back to the true position.
        offsets = [(0.0, 0.0)] + [
            (distance * math.cos(angle * math.pi / 4), distance * math.sin(angle * math.pi / 4))
            for distance in range(28, 281, 28) for angle in range(8)
        ]
        for point in sorted(points, key=lambda p: p.number):
            cx, cy = x_of(point.cost), y_of(point.score)
            for dx, dy in offsets:
                x, y = cx + dx, cy + dy
                if not (left + 11 <= x <= left + plot_w - 11 and top + 11 <= y <= top + plot_h - 11):
                    continue
                if all(math.hypot(x - px, y - py) >= 26 for px, py in label_positions.values()):
                    label_positions[point.number] = (x, y)
                    break
    # Draw low ranks last so the best model sits on top where markers overlap.
    for point in sorted(points, key=lambda p: -p.number):
        cx, cy = x_of(point.cost), y_of(point.score)
        if point.ci95:
            y1, y2 = y_of(point.ci95[1]), y_of(point.ci95[0])
            body.append(f'<line class="sc-whisker" x1="{cx:.1f}" y1="{y1:.1f}" x2="{cx:.1f}" y2="{y2:.1f}"/>')
            for y in (y1, y2):
                body.append(f'<line class="sc-whisker" x1="{cx - 5:.1f}" y1="{y:.1f}" x2="{cx + 5:.1f}" y2="{y:.1f}"/>')
        lx, ly = label_positions.get(point.number, (cx, cy))
        if (lx, ly) != (cx, cy):
            body.append(f'<line class="sc-whisker" x1="{cx:.1f}" y1="{cy:.1f}" x2="{lx:.1f}" y2="{ly:.1f}"/>')
            body.append(f'<circle class="sc-point" cx="{cx:.1f}" cy="{cy:.1f}" r="4"/>')
        radius = 11 if consistency else 13
        body.append(f'<circle class="sc-point" cx="{lx:.1f}" cy="{ly:.1f}" r="{radius}"><title>{escape(point.label)}</title></circle>')
        body.append(f'<text class="sc-num" x="{lx:.1f}" y="{ly + 5:.1f}" text-anchor="middle">{point.number}</text>')
    body.append("</svg>")
    return "".join(body)


def heat_style(score: float | None, lo: float = 0.0, hi: float = 1.0) -> str:
    """How strongly a grid cell mixes the accent into the card colour. The
    stylesheet does the mixing, so the cell reads in both themes. ``lo`` and
    ``hi`` stretch the scale over the scores on show; the curve spreads the
    upper part of the range, where most scores sit."""
    if score is None:
        return ""
    t = _clamp((score - lo) / (hi - lo)) if hi > lo else 1.0
    weight = 0.04 + 0.64 * t**1.5
    return f' style="--h:{weight * 100:.0f}%"'


# ---------------------------------------------------------------------------
# Dot rows: one HTML row per category, the graphic in a stretched SVG track.
# Markers are zero-length lines with round or square caps and a non-scaling
# stroke, so they stay round when the track stretches to any width.


@dataclass(frozen=True)
class Mark:
    x: float  # position along the track, 0..1
    shape: str = "dot"  # dot, square, ring, tick, bar
    tone: str = "hl"  # hl (accent), a, b, c (palette), muted, mean
    lo: float | None = None  # whisker ends, 0..1
    hi: float | None = None
    title: str = ""


@dataclass(frozen=True)
class DotRow:
    label_html: str
    aria: str  # plain-text description of the row for screen readers
    marks: tuple[Mark, ...]
    value_html: str = ""
    band: tuple[float, float] | None = None
    note_html: str = ""


def _p(value: float) -> str:
    return f"{_clamp(value) * 100:.2f}"


def _mark(mark: Mark) -> str:
    x = _p(mark.x)
    tone = f"tone-{mark.tone}"
    title = f"<title>{escape(mark.title)}</title>" if mark.title else ""
    parts = []
    if mark.shape == "bar":
        parts.append(f'<rect class="dt-bar {tone}" x="0" y="6" width="{x}" height="8"/>')
    if mark.lo is not None and mark.hi is not None:
        lo, hi = _p(mark.lo), _p(mark.hi)
        parts.append(f'<line class="dt-whisker" x1="{lo}" y1="10" x2="{hi}" y2="10" vector-effect="non-scaling-stroke"/>')
        for end in (lo, hi):
            parts.append(f'<line class="dt-whisker" x1="{end}" y1="6" x2="{end}" y2="14" vector-effect="non-scaling-stroke"/>')
    line = f'x1="{x}" y1="10" x2="{x}" y2="10" vector-effect="non-scaling-stroke"'
    if mark.shape == "dot":
        parts.append(f'<line class="dt-dot {tone}" {line}/>')
    elif mark.shape == "square":
        parts.append(f'<line class="dt-square {tone}" {line}/>')
    elif mark.shape == "ring":
        parts.append(f'<line class="dt-ring {tone}" {line}/><line class="dt-hole" {line}/>')
    elif mark.shape == "tick":
        parts.append(f'<line class="dt-tick {tone}" x1="{x}" y1="3" x2="{x}" y2="17" vector-effect="non-scaling-stroke"/>')
    return f"<g>{title}{''.join(parts)}</g>"


def dot_track(row: DotRow, grid: Sequence[float]) -> str:
    parts = [
        f'<svg class="dtrack" viewBox="0 0 100 20" preserveAspectRatio="none" role="img" aria-label="{escape(row.aria)}" focusable="false">',
        '<rect class="dt-base" x="0" y="9" width="100" height="2"/>',
    ]
    for pos in grid:
        parts.append(f'<line class="dt-grid" x1="{_p(pos)}" y1="1" x2="{_p(pos)}" y2="19" vector-effect="non-scaling-stroke"/>')
    if row.band:
        lo, hi = sorted(row.band)
        parts.append(f'<rect class="dt-band" x="{_p(lo)}" y="0" width="{(_clamp(hi) - _clamp(lo)) * 100:.2f}" height="20"/>')
    # Background marks first, so the marks that carry the reading sit on top.
    # Rings are wider than dots and drawn first, so a dot at the same value shows inside the ring.
    order = {"bar": 0, "muted": 1, "ring": 2}
    for mark in sorted(row.marks, key=lambda m: order.get(m.tone, order.get(m.shape, 3))):
        parts.append(_mark(mark))
    parts.append("</svg>")
    return "".join(parts)


def dot_rows(rows: Sequence[DotRow | str], ticks: Sequence[tuple[float, str]], *, top: int = 0, more_label: str = "rows") -> str:
    """A list of labelled tracks with a shared axis. A string in ``rows`` is a
    group heading. With ``top``, rows after the first ``top`` hide behind a
    'Show all' button (shown only when the script runs)."""
    grid = [pos for pos, _ in ticks]
    items = []
    counted = 0
    for row in rows:
        if isinstance(row, str):
            items.append(f'<li class="bars-group">{row}</li>')
            continue
        counted += 1
        more = ' class="more"' if top and counted > top else ""
        note = f'<span class="bar-note">{row.note_html}</span>' if row.note_html else ""
        items.append(
            f"<li{more}>"
            f'<span class="bar-label">{row.label_html}{note}</span>'
            f'<span class="bar-track">{dot_track(row, grid)}</span>'
            f'<span class="bar-value" aria-hidden="true">{row.value_html}</span></li>'
        )
    body = f'<ol class="bars dots">{"".join(items)}{_axis(ticks)}</ol>'
    if not top or counted <= top:
        return body
    more = f"Show all {counted} {more_label}"
    less = f"Show the first {top}"
    return (
        f'<div class="collapsible" data-collapsible>{body}<button type="button" class="show-all" data-show-all '
        f'aria-expanded="false" data-more="{escape(more)}" data-less="{escape(less)}">{escape(more)}</button></div>'
    )


def swatch(shape: str, tone: str) -> str:
    """A legend key drawn like the chart's marker."""
    if shape == "square":
        inner = f'<rect class="sw-fill tone-{tone}" x="2" y="2" width="10" height="10"/>'
    elif shape == "ring":
        inner = f'<circle class="sw-ring tone-{tone}" cx="7" cy="7" r="4"/>'
    elif shape == "tick":
        inner = f'<line class="sw-tick tone-{tone}" x1="7" y1="1" x2="7" y2="13"/>'
    elif shape == "band":
        inner = '<rect class="sw-band" x="0" y="1" width="14" height="12"/>'
    elif shape == "line":
        inner = f'<line class="sw-line tone-{tone}" x1="0" y1="7" x2="14" y2="7"/>'
    else:
        inner = f'<circle class="sw-fill tone-{tone}" cx="7" cy="7" r="5.5"/>'
    return f'<svg class="swatch" viewBox="0 0 14 14" aria-hidden="true" focusable="false">{inner}</svg>'


def nice_domain(values: Sequence[float], *, pad: float = 0.02, max_ticks: int = 6) -> tuple[float, float, float]:
    """A zoomed 0..1 score axis that holds every value: (low, high, step)."""
    lo_v, hi_v = max(0.0, min(values) - pad), min(1.0, max(values) + pad)
    for step in (0.05, 0.1, 0.2, 0.25):
        lo = math.floor(lo_v / step + 1e-9) * step
        hi = min(1.0, math.ceil(hi_v / step - 1e-9) * step)
        if hi <= lo:
            hi = min(1.0, lo + step)
            lo = hi - step
        if round((hi - lo) / step) + 1 <= max_ticks:
            return max(0.0, lo), hi, step
    return 0.0, 1.0, 0.25


def score_ticks(lo: float, hi: float, step: float) -> list[tuple[float, str]]:
    """Tick positions (0..1 along the track) and labels for a score axis."""
    count = int(round((hi - lo) / step))
    return [((i * step) / (hi - lo), f"{(lo + i * step) * 100:.0f}%") for i in range(count + 1)]


def log_axis(values: Sequence[float]) -> tuple[float, float, list[float]]:
    """Bounds and 1-2-5 ticks for a log axis that holds every positive value."""
    low, high = min(values), max(values)
    lo = 10.0 ** math.floor(math.log10(low))
    hi = 10.0 ** math.ceil(math.log10(high))
    if hi <= lo:
        hi = lo * 10
    return lo, hi, _ticks_log(lo, hi)


def money_axis(values: Sequence[float]) -> tuple[Callable[[float], float], list[tuple[float, str]], bool]:
    """A position function (0..1), labelled ticks, and whether the axis is
    logarithmic: it is when the values span ten times or more."""
    low, high = min(values), max(values)
    if low > 0 and high / low >= 10:
        lo, hi, ticks = log_axis(values)
        span = math.log10(hi) - math.log10(lo)

        def pos(value: float) -> float:
            return (math.log10(value) - math.log10(lo)) / span
    else:
        ticks = _ticks_linear(high * 1.05)
        top = ticks[-1]

        def pos(value: float) -> float:
            return value / top
    return pos, list(zip((pos(t) if t > 0 else 0.0 for t in ticks), _money_ticks(ticks))), low > 0 and high / low >= 10


# ---------------------------------------------------------------------------
# Line chart for small multiples: one category axis, one score axis.


@dataclass(frozen=True)
class Series:
    label: str
    values: tuple[float | None, ...]  # one per category; None leaves a gap
    tone: str = "model"  # model (thin, one per model) or median (bold, labelled)


def line_chart(
    categories: Sequence[str],
    notes: Sequence[str],
    series: Sequence[Series],
    *,
    band: Sequence[tuple[float, float] | None] = (),
    chart_id: str,
    title: str,
    desc: str,
) -> str:
    """Scores across ordered categories. Thin lines are single models, the
    bold line is labelled at its end, and the band spans lowest to highest."""
    values = [v for s in series for v in s.values if v is not None]
    values += [v for b in band if b for v in b]
    if not values or not categories:
        return '<p class="empty-note">Nothing to plot.</p>'
    width, height = 360, 236
    left, right, top, bottom = 42, 62, 12, 48
    plot_w, plot_h = width - left - right, height - top - bottom
    lo, hi, step = nice_domain(values, max_ticks=5)
    k = len(categories)

    def x_of(i: int) -> float:
        return left + (plot_w / 2 if k == 1 else i * plot_w / (k - 1))

    def y_of(v: float) -> float:
        return top + (1 - (_clamp(v) - lo) / (hi - lo)) * plot_h

    title_id, desc_id = f"{chart_id}-title", f"{chart_id}-desc"
    out = [
        f'<svg class="lines" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{title_id} {desc_id}">',
        f'<title id="{title_id}">{escape(title)}</title><desc id="{desc_id}">{escape(desc)}</desc>',
    ]
    for i in range(int(round((hi - lo) / step)) + 1):
        tick = lo + i * step
        y = y_of(tick)
        out.append(f'<line class="ln-grid" x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}"/>')
        out.append(f'<text class="ln-tick" x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{tick * 100:.0f}%</text>')
    for i, (cat, note) in enumerate(zip(categories, notes)):
        x = x_of(i)
        out.append(f'<text class="ln-cat" x="{x:.1f}" y="{top + plot_h + 19}" text-anchor="middle">{escape(cat)}</text>')
        out.append(f'<text class="ln-note" x="{x:.1f}" y="{top + plot_h + 36}" text-anchor="middle">{escape(note)}</text>')
    spans = [(i, b) for i, b in enumerate(band) if b]
    if len(spans) >= 2:
        upper = " ".join(f"{x_of(i):.1f},{y_of(b[1]):.1f}" for i, b in spans)
        lower = " ".join(f"{x_of(i):.1f},{y_of(b[0]):.1f}" for i, b in reversed(spans))
        out.append(f'<polygon class="ln-band" points="{upper} {lower}"/>')

    def segments(s: Series) -> list[list[tuple[float, float]]]:
        runs: list[list[tuple[float, float]]] = [[]]
        for i, v in enumerate(s.values):
            if v is None:
                runs.append([])
            else:
                runs[-1].append((x_of(i), y_of(v)))
        return [r for r in runs if r]

    for s in sorted(series, key=lambda s: s.tone == "median"):
        tip = "; ".join(f"{c} {v * 100:.1f}%" for c, v in zip(categories, s.values) if v is not None)
        cls = "ln-median" if s.tone == "median" else "ln-model"
        group = [f'<g class="ln-g {cls}-g"><title>{escape(s.label)}: {escape(tip)}</title>']
        for run in segments(s):
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in run)
            group.append(f'<polyline class="ln-hit" points="{pts}"/><polyline class="{cls}" points="{pts}"/>')
            radius = 3.5 if s.tone == "median" else 2
            group.extend(f'<circle class="{cls}-pt" cx="{x:.1f}" cy="{y:.1f}" r="{radius}"/>' for x, y in run)
        group.append("</g>")
        out.append("".join(group))
        if s.tone == "median":
            last = max((i for i, v in enumerate(s.values) if v is not None), default=None)
            if last is not None:
                out.append(
                    f'<text class="ln-label" x="{x_of(last) + 8:.1f}" y="{y_of(s.values[last]) + 4:.1f}">{escape(s.label)}</text>'
                )
    out.append("</svg>")
    return "".join(out)


def radar(labels: Sequence[str], values: Sequence[float], medians: Sequence[float], best: Sequence[float], title: str) -> str:
    """A shared 0..100% radial scale; values and wrapped labels at each vertex."""
    cx, cy, radius = 200, 175, 105
    angles = [-math.pi / 2 + i * 2 * math.pi / len(labels) for i in range(len(labels))]

    def point(i: int, distance: float) -> tuple[float, float]:
        return cx + math.cos(angles[i]) * distance, cy + math.sin(angles[i]) * distance

    def polygon(scores: Sequence[float]) -> str:
        return " ".join(f"{x:.2f},{y:.2f}" for i, value in enumerate(scores) for x, y in [point(i, radius * _clamp(value))])

    out = [
        '<svg class="radar" viewBox="0 0 400 350" role="img" '
        f'aria-label="{escape(title)}"><title>{escape(title)}</title>',
        '<desc>Scale: 0% at the centre to 100% at the outer ring. '
        + escape("; ".join(f"{label}: {pct(value)}, median {pct(median)}, best {pct(high)}" for label, value, median, high in zip(labels, values, medians, best)))
        + "</desc>",
    ]
    for fraction in (0.25, 0.5, 0.75, 1.0):
        out.append(f'<polygon class="radar-grid" points="{polygon([fraction] * len(labels))}"/>')
    for i in range(len(labels)):
        x, y = point(i, radius)
        out.append(f'<line class="radar-grid" x1="{cx}" y1="{cy}" x2="{x:.2f}" y2="{y:.2f}"/>')
    for tone, scores in (("best", best), ("median", medians), ("own", values)):
        out.append(f'<polygon class="radar-{tone}" points="{polygon(scores)}"/>')
    for i, (label, value) in enumerate(zip(labels, values)):
        x, y = point(i, radius * value)
        out.append(f'<circle class="radar-dot" cx="{x:.2f}" cy="{y:.2f}" r="3"/>')
        # Values sit outside the plotting ring, so a low score cannot collide
        # with a neighbour near the centre.
        tx, ty = point(i, radius + 20)
        out.append(f'<text class="radar-value" x="{tx:.2f}" y="{ty + 4:.2f}" text-anchor="middle">{pct(value)}</text>')
        lx, ly = point(i, radius + 48)
        words = label.split()
        midpoint = max(1, len(words) // 2)
        lines = [" ".join(words[:midpoint]), " ".join(words[midpoint:])] if len(label) > 14 else [label]
        out.append(f'<text class="radar-label" x="{lx:.2f}" y="{ly - 5:.2f}" text-anchor="middle">')
        out.extend(f'<tspan x="{lx:.2f}" dy="{0 if j == 0 else 14}">{escape(line)}</tspan>' for j, line in enumerate(lines))
        out.append("</text>")
    out.append("</svg>")
    return "".join(out)
