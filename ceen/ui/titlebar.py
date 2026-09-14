"""Custom title bar — the dark strip that replaces the white Windows one.

The viewport is created with decorated=False (no OS frame at all), so
THIS bar is the window's face: a brand dot + name on the left, then
minimize and close on the right. Dragging the empty middle of the bar
moves the window (a tiny per-frame "follow the mouse" loop).

Everything here is intentionally generic: take it, restyle it, reuse it.
"""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ceen.config import APP_VERSION
from ceen.ui.theme import c

BAR_H = 30                    # strip height that counts as "the bar"
_BTN_W = 34                   # width of the _ and X buttons (no-drag zone)
_dragging = False             # is the user currently dragging the bar?
_grab_offset = (0.0, 0.0)     # cursor-to-window-corner offset at grab
_title_w = 90.0               # rendered width of the brand text (measured)
_version_w = 26.0             # rendered width of the version badge


def _screen_cursor() -> tuple:
    """The cursor's TRUE on-screen position (Windows), independent of
    where our window is — this is what makes dragging glitch-free."""
    try:
        import ctypes

        class _Pt(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
        pt = _Pt()
        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
        return float(pt.x), float(pt.y)
    except Exception:  # noqa: BLE001 — non-Windows fallback below
        return None


def add_title_bar() -> None:
    """Build the bar inside the current window (call first, at the top).

    Layout: [ dot  ceen proxy  <spring>  _  X ]
    The drag zone is the whole top strip EXCEPT the two buttons.
    """
    with dpg.group(horizontal=True, tag="titlebar"):
        dpg.add_spacer(width=12)
        dpg.add_drawlist(width=14, height=14, tag="tb_logo")
        dpg.add_spacer(width=8)
        dpg.add_text("ceen proxy", tag="tb_title")
        dpg.add_text(f"v{APP_VERSION}", tag="tb_version")   # muted badge
        dpg.add_spacer(width=120, tag="tb_spring")   # stretched per frame
        dpg.add_button(label="_", tag="tb_min", width=_BTN_W, height=BAR_H,
                       callback=_minimize)
        dpg.add_button(label="X", tag="tb_close", width=_BTN_W, height=BAR_H,
                       callback=_close_app)
    _style_bar()
    _measure_title()
    with dpg.handler_registry():
        dpg.add_mouse_move_handler(callback=_on_mouse_move)


def tick_titlebar() -> None:
    """Keep the buttons pinned to the right edge (cheap, once a frame).

    Called from the app's update loop so the spring spacer always fills
    the gap between the title and the buttons at any window width.
    """
    try:
        w = dpg.get_viewport_client_width()
        spring = w - 28 - (12 + 14 + 8 + _title_w + _version_w) - 2 * _BTN_W
        dpg.set_item_width("tb_spring", max(8, round(spring)))
    except Exception:  # noqa: BLE001 — cosmetic; never break the frame
        pass


def _measure_title() -> None:
    """Ask the font how wide 'ceen proxy' really is (no guessing)."""
    global _title_w, _version_w
    try:
        from ceen.ui import theme as _theme
        _title_w = dpg.get_text_size("ceen proxy",
                                     font=_theme.FONT_BOLD)[0]
        _version_w = dpg.get_text_size(f"v{APP_VERSION}",
                                       font=_theme.FONT_SMALL)[0] + 5
    except Exception:  # noqa: BLE001 — the default estimate is fine
        pass


def _style_bar() -> None:
    """Flat dark bar; subtle hover color on the two window buttons."""
    with dpg.theme(tag="tb_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 0, 0)
            dpg.add_theme_style(dpg.mvStyleVar_FramePadding, 0, 0)
    dpg.bind_item_theme("titlebar", "tb_theme")
    for tag, hovered in (("tb_min", c("panel_hi")), ("tb_close", c("red"))):
        with dpg.theme(tag=f"{tag}_theme"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, hovered)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, hovered)
                dpg.add_theme_color(dpg.mvThemeCol_Text, c("muted"))
        dpg.bind_item_theme(tag, f"{tag}_theme")
    # the little brand dot (drawn, not an image file)
    dpg.draw_circle([7, 7], 6, color=(0, 0, 0, 0), fill=c("accent"),
                    parent="tb_logo")
    dpg.bind_item_font("tb_title", _font_bold())
    # version badge: small, muted, with a breathing gap after the name
    dpg.bind_item_font("tb_version", _font_small())
    with dpg.theme(tag="tb_version_theme"):
        with dpg.theme_component(dpg.mvAll):
            dpg.add_theme_color(dpg.mvThemeCol_Text, c("faint"))
    dpg.bind_item_theme("tb_version", "tb_version_theme")


def _font_bold() -> str:
    """The bold font tag (falls back to the default if fonts missing)."""
    try:
        from ceen.ui import theme as _theme
        return _theme.FONT_BOLD
    except Exception:  # noqa: BLE001
        return 0


def _font_small() -> str:
    """The small font tag (falls back to the default if fonts missing)."""
    try:
        from ceen.ui import theme as _theme
        return _theme.FONT_SMALL
    except Exception:  # noqa: BLE001
        return 0


def _minimize() -> None:
    dpg.minimize_viewport()


def _close_app() -> None:
    """Close like the OS X button would (the shutdown guard still runs)."""
    dpg.stop_dearpygui()


def _on_mouse_move() -> None:
    """Drag the window by the empty middle of the title bar.

    Why this is glitch-free: the window is placed at
        (true screen cursor) - (offset captured at grab)
    every frame. The screen cursor comes from the OS, not from the
    moving window, so there is no feedback loop to oscillate.
    """
    global _dragging, _grab_offset
    if not dpg.is_mouse_button_down(0):
        _dragging = False
        return
    mx, my = dpg.get_mouse_pos(local=False)      # window-relative (grab test)
    if not _dragging:
        # grab starts only in the top strip, away from the two buttons
        try:
            w = dpg.get_viewport_client_width()
        except Exception:  # noqa: BLE001
            w = 400
        strip = my <= BAR_H + 6
        away_from_buttons = mx < w - 2 * _BTN_W - 4
        if strip and away_from_buttons:
            scr = _screen_cursor()
            if scr is not None:
                _dragging = True
                wx, wy = dpg.get_viewport_pos()
                _grab_offset = (scr[0] - wx, scr[1] - wy)
        return
    scr = _screen_cursor()
    if scr is None:              # non-Windows: no reliable dragging
        _dragging = False
        return
    dpg.set_viewport_pos([scr[0] - _grab_offset[0],
                          scr[1] - _grab_offset[1]])
