#!/usr/bin/env python3
"""Mock-up animated bar-chart GIFs for Teanga Bench tweets.

Reads the real leaderboard at /home/box/teanga-bench/results/leaderboard.json.
Does not modify the repo.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

LEADERBOARD = Path("/home/box/teanga-bench/results/leaderboard.json")
OUT_DIR = Path("/workspace/teanga-gif")

W, H = 1200, 675
SCALE = 2  # render retina, then downscale
FPS = 25
GROW_FRAMES = 25  # 1.0s
FADE_FRAMES = 13  # 0.52s
HOLD_SECONDS = 4.0
BG = (250, 249, 246)  # #FAF9F6
INK = (28, 27, 25)
MUTED = (107, 104, 96)
MUTED_SOFT = (168, 164, 155)
GRID = (226, 223, 216)
RULE = (226, 223, 216)

NEWSREADER = Path(
    "/usr/share/fonts/truetype/sand-box/google/Newsreader/Newsreader-VariableFont_opsz,wght.ttf"
)
INTER = Path(
    "/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf"
)

# Pastel fill, slightly darker outline; saturated fill/outline for the highlighted model.
LAB_COLORS = {
    "google": {
        "fill": (185, 212, 240),
        "outline": (123, 163, 204),
        "hot_fill": (26, 115, 232),
        "hot_outline": (18, 80, 168),
        "label": (26, 115, 232),
    },
    "anthropic": {
        "fill": (245, 205, 176),
        "outline": (212, 160, 122),
        "hot_fill": (224, 122, 69),
        "hot_outline": (186, 90, 42),
        "label": (186, 90, 42),
    },
    "openai": {
        "fill": (199, 198, 195),
        "outline": (150, 148, 144),
        "hot_fill": (47, 47, 45),
        "hot_outline": (26, 26, 24),
        "label": (47, 47, 45),
    },
    "deepseek": {
        "fill": (201, 196, 235),
        "outline": (155, 148, 201),
        "hot_fill": (79, 70, 229),
        "hot_outline": (55, 48, 163),
        "label": (79, 70, 229),
    },
    "qwen": {
        "fill": (217, 196, 234),
        "outline": (176, 146, 201),
        "hot_fill": (124, 58, 237),
        "hot_outline": (91, 33, 182),
        "label": (124, 58, 237),
    },
    "moonshot": {
        "fill": (181, 221, 216),
        "outline": (123, 181, 174),
        "hot_fill": (13, 148, 136),
        "hot_outline": (15, 118, 110),
        "label": (13, 148, 136),
    },
    "other": {
        "fill": (212, 208, 203),
        "outline": (168, 164, 158),
        "hot_fill": (107, 104, 96),
        "hot_outline": (74, 72, 66),
        "label": (107, 104, 96),
    },
}

DISPLAY_NAMES = {
    "anthropic/claude-fable-5.2": "Claude Fable 5.2",
    "google/gemini-4-hydrogen": "Gemini 4 Hydrogen",
    "openai/gpt-6-astra": "GPT-6 Astra",
    "google/gemini-4-argon": "Gemini 4 Argon",
    "moonshotai/kimi-k3.1-pro": "Kimi K3.1 Pro",
    "deepseek/deepseek-v4.1-flash-1017": "DeepSeek V4.1 Flash",
    "openai/gpt-6-luna": "GPT-6 Luna",
    "anthropic/claude-haiku-5.5": "Claude Haiku 5.5",
    "qwen/qwen3.8-flash": "Qwen 3.8 Flash",
}

FAMILY_PREFIX = {
    "google": "google",
    "anthropic": "anthropic",
    "openai": "openai",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "moonshotai": "moonshot",
    "moonshot": "moonshot",
}

SUITE_META = {
    "blas": {
        "badge": "BLAS",
        "subtitle": "Teanga Bench · Blas suite · overall accuracy",
        "watermark": "research.blasapp.com",
        "headline_suffix": "leads on Celtic languages",
        "stem": "blas-overall",
    },
    "tonada": {
        "badge": "TONADA",
        "subtitle": "Teanga Bench · Tonada suite · overall accuracy",
        "watermark": "research.tonadaapp.com",
        "headline_suffix": "leads on English tutoring",
        "stem": "tonada-overall",
    },
}


@dataclass
class Row:
    model_id: str
    name: str
    family: str
    score: float  # 0-100, one decimal as published
    raw: float
    highlight: bool
    generated_at: str


def load_font(path: Path, size: float, weight: int = 400, opsz: float | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(str(path), size=size)
    try:
        axes = font.get_variation_axes()
        values = []
        for ax in axes:
            name = ax["name"].decode() if isinstance(ax["name"], bytes) else ax["name"]
            key = name.lower().replace(" ", "")
            if key in {"wght", "weight"}:
                val = weight
            elif key in {"opsz", "opticalsize"}:
                val = size if opsz is None else opsz
            else:
                val = ax["default"]
            val = max(ax["minimum"], min(ax["maximum"], val))
            values.append(val)
        font.set_variation_by_axes(values)
    except OSError:
        pass
    return font


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1.0 - (1.0 - t) ** 3


def display_name(model_id: str) -> str:
    if model_id in DISPLAY_NAMES:
        return DISPLAY_NAMES[model_id]
    slug = model_id.split("/", 1)[-1]
    parts = slug.replace("_", "-").split("-")
    pretty = []
    for part in parts:
        if part.lower() in {"gpt", "qwen"} or any(ch.isdigit() for ch in part):
            pretty.append(part.upper() if part.isalpha() and len(part) <= 4 else part)
        else:
            pretty.append(part.capitalize())
    # Fix common tokens
    out = " ".join(pretty)
    out = out.replace("Gpt", "GPT").replace("Gpt-", "GPT-")
    return out


def family_of(model: dict) -> str:
    fam = (model.get("family") or "").lower()
    if fam in LAB_COLORS:
        return fam
    prefix = model["model"].split("/", 1)[0].lower()
    return FAMILY_PREFIX.get(prefix, "other")


def pct_published(score: float) -> float:
    """Match the published leaderboard: one decimal place of the percentage."""
    return round(score * 100, 1)


def load_rows(suite: str) -> tuple[list[Row], str]:
    data = json.loads(LEADERBOARD.read_text())
    models = [m for m in data["models"] if m.get("status") == "complete" and m.get("ranked")]
    if not models:
        raise SystemExit("no ranked complete models in the leaderboard")

    newest = max(models, key=lambda m: m["generated_at"])
    highlight_id = newest["model"]

    rows: list[Row] = []
    for m in models:
        suites = m.get("suites") or {}
        if suite not in suites or suites[suite].get("score") is None:
            continue
        raw = float(suites[suite]["score"])
        rows.append(
            Row(
                model_id=m["model"],
                name=display_name(m["model"]),
                family=family_of(m),
                score=pct_published(raw),
                raw=raw,
                highlight=(m["model"] == highlight_id),
                generated_at=m["generated_at"],
            )
        )
    rows.sort(key=lambda r: (-r.raw, r.name.lower()))
    return rows, highlight_id


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[float, float],
    font: ImageFont.FreeTypeFont,
    fill,
    tracking: float = 0,
    anchor: str = "lt",
) -> None:
    if not tracking:
        draw.text(xy, text, font=font, fill=fill, anchor=anchor)
        return
    widths = []
    for ch in text:
        widths.append(draw.textlength(ch, font=font))
    total = sum(widths) + tracking * (len(text) - 1)
    x, y = xy
    if "r" in anchor:
        x -= total
    elif "m" in anchor:
        x -= total / 2
    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill, anchor="lt" if "t" in anchor else ("ls" if "s" in anchor else "lm"))
        x += w + tracking


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix_color(c1, c2, t: float):
    return tuple(int(round(lerp(a, b, t))) for a, b in zip(c1, c2))


class Chart:
    def __init__(self, suite: str, rows: list[Row]):
        self.suite = suite
        self.rows = rows
        self.meta = SUITE_META[suite]
        self.top = rows[0]
        self.headline = f"{self.top.name} {self.meta['headline_suffix']}"
        self.s = SCALE
        self.cw = W * SCALE
        self.ch = H * SCALE

        # Layout in CSS pixels (1x), multiplied at draw time.
        self.margin_x = 48
        self.margin_right = 48
        self.bar_left = 318
        self.bar_right = 1120  # room for labels just past the bar
        self.chart_top = 168
        self.chart_bottom = 628
        self.bar_h = 28
        self.radius = 8

    def px(self, v: float) -> int:
        return int(round(v * self.s))

    def font(self, kind: str, size: float, weight: int, opsz: float | None = None) -> ImageFont.FreeTypeFont:
        path = NEWSREADER if kind == "serif" else INTER
        return load_font(path, size * self.s, weight=weight, opsz=(opsz if opsz is None else opsz * self.s))

    def row_geometry(self) -> list[tuple[Row, float, float]]:
        n = len(self.rows)
        span = self.chart_bottom - self.chart_top
        slot = span / n
        out = []
        for i, row in enumerate(self.rows):
            cy = self.chart_top + slot * (i + 0.5)
            y = cy - self.bar_h / 2
            out.append((row, y, cy))
        return out

    def bar_width(self, score: float, progress: float) -> float:
        max_w = self.bar_right - self.bar_left
        return max_w * (score / 100.0) * progress

    def render(self, progress: float, label_alpha: float) -> Image.Image:
        img = Image.new("RGB", (self.cw, self.ch), BG)
        d = ImageDraw.Draw(img)
        s = self.s

        brand = self.font("sans", 11, 600, opsz=14)
        headline = self.font("serif", 40, 600, opsz=60)
        # Shrink headline if it would overflow.
        max_head_w = (W - self.margin_x * 2) * s
        size = 40
        while headline.getlength(self.headline) > max_head_w and size > 28:
            size -= 1
            headline = self.font("serif", size, 600, opsz=60)
        sub = self.font("sans", 15, 450, opsz=14)
        name_font = self.font("sans", 15, 650, opsz=16)
        name_font_hot = self.font("sans", 15, 700, opsz=16)
        pct_font = self.font("sans", 15, 650, opsz=16)
        axis_font = self.font("sans", 11, 500, opsz=14)
        water_font = self.font("sans", 12, 450, opsz=14)
        badge_font = self.font("sans", 9, 700, opsz=14)

        # Branding
        draw_tracked(
            d,
            "TEANGA BENCH",
            (self.px(self.margin_x), self.px(28)),
            brand,
            MUTED,
            tracking=2.4 * s,
            anchor="lt",
        )
        badge = self.meta["badge"]
        # measure tracked width for right alignment
        b_w = sum(d.textlength(ch, font=brand) for ch in badge) + 2.4 * s * (len(badge) - 1)
        draw_tracked(
            d,
            badge,
            (self.px(W - self.margin_right) - b_w, self.px(28)),
            brand,
            MUTED,
            tracking=2.4 * s,
            anchor="lt",
        )

        # Headline + subtitle
        d.text((self.px(self.margin_x), self.px(62)), self.headline, font=headline, fill=INK, anchor="lt")
        d.text((self.px(self.margin_x), self.px(116)), self.meta["subtitle"], font=sub, fill=MUTED, anchor="lt")

        # Light rule under the header
        d.line(
            [(self.px(self.margin_x), self.px(146)), (self.px(W - self.margin_right), self.px(146))],
            fill=RULE,
            width=max(1, self.px(1)),
        )

        # Vertical gridlines and axis labels
        for tick in (0, 25, 50, 75, 100):
            x = self.bar_left + (self.bar_right - self.bar_left) * (tick / 100.0)
            d.line(
                [(self.px(x), self.px(self.chart_top - 6)), (self.px(x), self.px(self.chart_bottom))],
                fill=GRID,
                width=max(1, self.px(1)),
            )
            d.text((self.px(x), self.px(self.chart_top - 12)), f"{tick}%", font=axis_font, fill=MUTED_SOFT, anchor="mb")

        geos = self.row_geometry()
        name_right = self.bar_left - 16

        # Bars and names first, labels later so labels sit on top.
        for row, y, cy in geos:
            colors = LAB_COLORS.get(row.family, LAB_COLORS["other"])
            fill = colors["hot_fill"] if row.highlight else colors["fill"]
            outline = colors["hot_outline"] if row.highlight else colors["outline"]
            w = self.bar_width(row.score, progress)

            # Model name, right-aligned to the bars.
            nf = name_font_hot if row.highlight else name_font
            name_fill = INK if not row.highlight else colors["hot_outline"]
            d.text((self.px(name_right), self.px(cy)), row.name, font=nf, fill=name_fill, anchor="rm")

            if row.highlight:
                # Small NEW pill to the left of the name.
                name_w = d.textlength(row.name, font=nf)
                pill_h = 14
                pill_text = "NEW"
                pad_x = 5
                tw = d.textlength(pill_text, font=badge_font)
                pill_w = tw + pad_x * 2 * s / s  # in 1x, compute properly below
                pill_w = (tw / s) + 10
                gap = 8
                pill_right = name_right - (name_w / s) - gap
                pill_left = pill_right - pill_w
                # If the name is long, tuck the pill just left of the margin by shrinking gap visually;
                # still draw it even if it sits close to the edge.
                px1, py1 = self.px(pill_left), self.px(cy - pill_h / 2)
                px2, py2 = self.px(pill_right), self.px(cy + pill_h / 2)
                d.rounded_rectangle(
                    [px1, py1, px2, py2],
                    radius=self.px(pill_h / 2),
                    fill=colors["hot_fill"],
                )
                d.text(
                    ((px1 + px2) / 2, (py1 + py2) / 2),
                    pill_text,
                    font=badge_font,
                    fill=(255, 255, 255),
                    anchor="mm",
                )

            if w <= 0.6:
                continue
            radius = min(self.radius, w / 2, self.bar_h / 2)
            outline_w = 3 if row.highlight else 2
            d.rounded_rectangle(
                [self.px(self.bar_left), self.px(y), self.px(self.bar_left + w), self.px(y + self.bar_h)],
                radius=self.px(radius),
                fill=fill,
                outline=outline,
                width=self.px(outline_w),
            )

        # Percentage labels, just past each bar end.
        if label_alpha > 0:
            for row, y, cy in geos:
                final_w = self.bar_width(row.score, 1.0)
                grown_w = self.bar_width(row.score, progress)
                # Sit just past the current (or final) bar end.
                x = self.bar_left + max(grown_w, final_w * max(progress, 0.001)) + 10
                text = f"{row.score:.1f}%"
                # Pop: slight rise + fade.
                pop = 1.0 - (1.0 - label_alpha) ** 2
                y_off = (1.0 - pop) * 4
                alpha = int(round(255 * label_alpha))
                color = mix_color(BG, INK, label_alpha)
                d.text((self.px(x), self.px(cy - y_off)), text, font=pct_font, fill=color, anchor="lm")

        # Watermark
        d.text(
            (self.px(self.margin_x), self.px(652)),
            self.meta["watermark"],
            font=water_font,
            fill=MUTED_SOFT,
            anchor="lt",
        )

        return img.resize((W, H), Image.Resampling.LANCZOS)


def collect_frames(chart: Chart) -> list[Image.Image]:
    frames: list[Image.Image] = []
    for i in range(GROW_FRAMES):
        t = (i + 1) / GROW_FRAMES
        frames.append(chart.render(progress=ease_out_cubic(t), label_alpha=0.0))
    for i in range(FADE_FRAMES):
        t = (i + 1) / FADE_FRAMES
        # ease-out on the fade/pop
        frames.append(chart.render(progress=1.0, label_alpha=ease_out_cubic(t)))
    return frames


def save_png(img: Image.Image, path: Path) -> None:
    img.save(path, "PNG", optimize=True)


def save_gif(frames: list[Image.Image], path: Path) -> None:
    # Build a shared palette from the final frame (most colours present) to avoid flicker.
    final = frames[-1].convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
    quantized = [im.quantize(palette=final, dither=Image.Dither.NONE) for im in frames]
    durations = [int(1000 / FPS)] * (len(frames) - 1) + [int(HOLD_SECONDS * 1000)]
    quantized[0].save(
        path,
        save_all=True,
        append_images=quantized[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=2,
    )
    # Try a second pass with ffmpeg palette if the file is large or if ffmpeg is available
    # and we want tighter compression. If over 5MB, recompress.
    if path.stat().st_size > 5 * 1024 * 1024:
        recompress_gif_ffmpeg(frames, path)


def recompress_gif_ffmpeg(frames: list[Image.Image], path: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        for i, im in enumerate(frames):
            im.save(tdir / f"f{i:04d}.png")
        # concat with hold on last frame
        lst = tdir / "list.txt"
        lines = []
        dt = 1 / FPS
        for i in range(len(frames)):
            lines.append(f"file '{tdir / f'f{i:04d}.png'}'")
            lines.append(f"duration {HOLD_SECONDS if i == len(frames) - 1 else dt:.4f}")
        lines.append(f"file '{tdir / f'f{len(frames) - 1:04d}.png'}'")
        lst.write_text("\n".join(lines) + "\n")
        pal = tdir / "palette.png"
        tmp = tdir / "out.gif"
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-vf", "palettegen=max_colors=64:stats_mode=diff",
                str(pal),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.check_call(
            [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                "-i", str(pal),
                "-lavfi", "paletteuse=dither=none:diff_mode=rectangle",
                "-loop", "0",
                str(tmp),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        shutil.copy(tmp, path)


def save_mp4(frames: list[Image.Image], path: Path) -> None:
    with tempfile.TemporaryDirectory() as td:
        tdir = Path(td)
        for i, im in enumerate(frames):
            im.save(tdir / f"f{i:04d}.png")
        # 675 is odd; pad 1px so yuv420p is valid.
        bg_hex = "0x{:02X}{:02X}{:02X}".format(*BG)
        vf = (
            f"tpad=stop_mode=clone:stop_duration={HOLD_SECONDS},"
            f"pad=1200:676:0:0:color={bg_hex}"
        )
        subprocess.check_call(
            [
                "ffmpeg", "-y",
                "-framerate", str(FPS),
                "-i", str(tdir / "f%04d.png"),
                "-vf", vf,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-crf", "18",
                "-movflags", "+faststart",
                str(path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def export_previews(frames: list[Image.Image], stem: str) -> None:
    preview_dir = OUT_DIR / "previews"
    preview_dir.mkdir(exist_ok=True)
    # Mid-growth (~0.5s, frame 12 of 25), first label frame, and final.
    mid = frames[max(0, GROW_FRAMES // 2 - 1)]
    first_label = frames[GROW_FRAMES]
    final = frames[-1]
    save_png(mid, preview_dir / f"{stem}-mid-growth.png")
    save_png(first_label, preview_dir / f"{stem}-labels-start.png")
    save_png(final, preview_dir / f"{stem}-final.png")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Reading {LEADERBOARD}")
    for suite in ("blas", "tonada"):
        rows, highlight_id = load_rows(suite)
        if not rows:
            print(f"skip {suite}: no scores")
            continue
        chart = Chart(suite, rows)
        print(f"\n=== {suite.upper()} ===")
        print(f"headline: {chart.headline}")
        print(f"highlight (newest run): {highlight_id}")
        for r in rows:
            mark = "  ← NEW" if r.highlight else ""
            print(f"  {r.score:5.1f}%  {r.name:24s}  {r.family}{mark}")
        print("rendering frames…")
        frames = collect_frames(chart)
        stem = chart.meta["stem"]
        png_path = OUT_DIR / f"{stem}.png"
        gif_path = OUT_DIR / f"{stem}.gif"
        mp4_path = OUT_DIR / f"{stem}.mp4"
        save_png(frames[-1], png_path)
        print(f"  wrote {png_path}")
        save_gif(frames, gif_path)
        print(f"  wrote {gif_path}  ({gif_path.stat().st_size / 1024:.0f} KB)")
        save_mp4(frames, mp4_path)
        print(f"  wrote {mp4_path}  ({mp4_path.stat().st_size / 1024:.0f} KB)")
        export_previews(frames, stem)
    print("\ndone.")


if __name__ == "__main__":
    main()
