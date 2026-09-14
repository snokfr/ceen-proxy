"""The look of Ceen Proxy — Windscribe-style dark theme for Dear PyGui.

All colors, the font, and the global "theme" (rounded corners, dark
window backgrounds, hover states) live here so the rest of the UI never
hard-codes a color. Change a value in PALETTE and the whole app follows.
"""

from __future__ import annotations

import os

import dearpygui.dearpygui as dpg

# ── palette (RGB tuples, 0-255) — sampled from the Windscribe look ───────────
PALETTE = {
    "bg":        (14, 16, 20),      # near-black window
    "panel":     (22, 25, 31),      # cards / list rows
    "panel_hi":  (30, 34, 42),      # hovered rows
    "border":    (44, 49, 60),
    "text":      (240, 242, 247),
    "muted":     (140, 147, 160),
    "faint":     (90, 96, 108),
    "accent":    (66, 133, 244),    # Windscribe blue
    "accent_dn": (52, 108, 199),
    "green":     (46, 204, 113),
    "green_dn":  (32, 160, 90),
    "amber":     (255, 168, 46),
    "red":       (235, 77, 61),
    "white":     (255, 255, 255),
    "black":     (10, 11, 14),
}


def c(key: str):
    """Shortcut: color by name, e.g. c('accent')."""
    return PALETTE[key]


def blend_rgb(a, b, t: float):
    """Mix two colors: t=0 -> a, t=1 -> b (for smooth pulses)."""
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


# Fonts are discovered once and reused everywhere (tag stored on module).
FONT_TAG = "ceen_font"
FONT_BOLD = "ceen_font_bold"
FONT_SMALL = "ceen_font_small"
FONT_TITLE = "ceen_font_title"

# Windows ships these; fall back gracefully anywhere else.
_FONT_CANDIDATES = ["segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"]
_FONT_DIRS = [r"C:\Windows\Fonts", "/System/Library/Fonts",
              "/usr/share/fonts/truetype/dejavu"]


def _find_font(bold: bool = False) -> str | None:
    """First font file that exists on this computer (bold preferred)."""
    names = (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"]
             if bold else
             ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"]) + _FONT_CANDIDATES
    for d in _FONT_DIRS:
        for n in names:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None


def setup_fonts() -> None:
    """Load real fonts (default dpg font is tiny bitmap type)."""
    with dpg.font_registry():
        base = _find_font(False)
        if base:
            dpg.add_font(base, 15, tag=FONT_TAG)
            dpg.add_font(base, 12, tag=FONT_SMALL)
            bold = _find_font(True) or base
            dpg.add_font(bold, 17, tag=FONT_BOLD)
            dpg.add_font(bold, 21, tag=FONT_TITLE)
            dpg.bind_font(FONT_TAG)


def setup_theme() -> None:
    """One global theme: dark surfaces, rounded corners, blue highlights."""
    with dpg.theme() as theme:
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_WindowBg, c("bg"))
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, c("bg"))
            dpg.add_theme_color(dpg.mvThemeCol_Text, c("text"))
            dpg.add_theme_color(dpg.mvThemeCol_Border, c("bg"))
            dpg.add_theme_color(dpg.mvThemeCol_PopupBg, c("panel"))
            dpg.add_theme_color(dpg.mvThemeCol_TitleBg, c("bg"))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, c("panel"))
            dpg.add_theme_color(dpg.mvThemeCol_CheckMark, c("accent"))
            dpg.add_theme_style(dpg.mvStyleVar_WindowRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_ChildRounding, 10)
            dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 8)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 8, 6)
            dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 14, 12)
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 6)
    dpg.bind_theme(theme)


def style_button(tag, solid: bool = False, color=None) -> None:
    """Give one button a flat pill look (filled or ghost)."""
    main = color or (c("accent") if solid else c("panel"))
    hover = (c("accent_dn") if solid else c("panel_hi"))
    with dpg.theme(tag=f"btn_theme_{tag}"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, main)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hover)
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive,
                                c("accent_dn") if solid else c("border"))
            dpg.add_theme_color(dpg.mvThemeCol_Text,
                                c("white") if solid else c("text"))
    dpg.bind_item_theme(tag, f"btn_theme_{tag}")


def style_child(tag, bg=None) -> None:
    """Round card look for a child region."""
    with dpg.theme(tag=f"child_theme_{tag}"):
        with dpg.theme_component(dpg.mvChildWindow):
            dpg.add_theme_color(dpg.mvThemeCol_ChildBg, bg or c("panel"))
            dpg.add_theme_color(dpg.mvThemeCol_Border, c("bg"))
    dpg.bind_item_theme(tag, f"child_theme_{tag}")


def style_input(tag) -> None:
    """Dark, rounded search box."""
    with dpg.theme(tag=f"input_theme_{tag}"):
        with dpg.theme_component(dpg.mvInputText):
            dpg.add_theme_color(dpg.mvThemeCol_FrameBg, c("panel"))
            dpg.add_theme_color(dpg.mvThemeCol_FrameBgHovered, c("panel_hi"))
            dpg.add_theme_color(dpg.mvThemeCol_Text, c("text"))
    dpg.bind_item_theme(tag, f"input_theme_{tag}")
