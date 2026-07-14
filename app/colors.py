"""Shared color assignment, per the dataviz skill's color formula.

Sequential (magnitude, e.g. accessibility_index): one hue, light -> dark.
Categorical (identity, e.g. brand lines): fixed hue order, never cycled by
selection - a brand keeps its color regardless of which other brands are
selected, so filtering never repaints the survivors. Both ramps are the
skill's validated reference palette (references/palette.md), unchanged.
"""

import hashlib

SEQUENTIAL_LIGHT = (0xCD, 0xE2, 0xFB)  # ramp step 100
SEQUENTIAL_DARK = (0x0D, 0x36, 0x6B)  # ramp step 700

CATEGORICAL = [
    "#2a78d6",  # 1 blue
    "#1baf7a",  # 2 aqua
    "#eda100",  # 3 yellow
    "#008300",  # 4 green
    "#4a3aa7",  # 5 violet
    "#e34948",  # 6 red
    "#e87ba4",  # 7 magenta
    "#eb6834",  # 8 orange
]

MUTED_INK = "#898781"


def sequential_color(value: float, vmin: float, vmax: float) -> str:
    t = 0.0 if vmax == vmin else (value - vmin) / (vmax - vmin)
    t = max(0.0, min(1.0, t))
    r = round(SEQUENTIAL_LIGHT[0] + t * (SEQUENTIAL_DARK[0] - SEQUENTIAL_LIGHT[0]))
    g = round(SEQUENTIAL_LIGHT[1] + t * (SEQUENTIAL_DARK[1] - SEQUENTIAL_LIGHT[1]))
    b = round(SEQUENTIAL_LIGHT[2] + t * (SEQUENTIAL_DARK[2] - SEQUENTIAL_LIGHT[2]))
    return f"#{r:02x}{g:02x}{b:02x}"


def brand_color(brand_key: str) -> str:
    index = int(hashlib.md5(brand_key.encode("utf-8")).hexdigest(), 16) % len(CATEGORICAL)
    return CATEGORICAL[index]
