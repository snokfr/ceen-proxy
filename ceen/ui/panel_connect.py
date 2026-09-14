"""The CONNECT screen — compact, professional, everything visible.

Layout (fits a 380x590 window with NO scrolling to reach the buttons):
    [ ceen            status pill ]
    [ power ring ]  [ tunnel info + sparkline ]
    [ big location line      ]
    [ Network > ip           ]
    [ ALL LOCATIONS | n      ]
    [ (scrollable server list — expandable, see server_list.py) ]
    [ CONNECT FASTEST   PROXY CHECKER ]   <- always on screen

The power ring is the ONLY on/off switch and now uses a real item click
handler (bind_item_handler_registry), so the whole ring area is tappable.
"""

from __future__ import annotations

import math
import time

import dearpygui.dearpygui as dpg

from ceen.ui import server_list, theme
from ceen.ui.sparkline import Sparkline
from ceen.ui.theme import c

_RING = "power_ring"
_SEG = 26                       # arc pieces forming the gradient ring
_C = 59.0                       # ring center (= drawlist size / 2)
_R = 45.0                       # ring radius (everything scales off this)


# ── build ────────────────────────────────────────────────────────────────
def build_connect_panel(app) -> None:
    """Create every widget of the Connect screen."""
    t = app.tags
    with dpg.child_window(tag=t["connect_root"], autosize_y=True,
                          no_scrollbar=True, border=False):
        # header: wordmark left, status pill right (one axis)
        with dpg.group(horizontal=True):
            dpg.add_text("ceen", tag="wordmark")
            dpg.bind_item_font(dpg.last_item(), theme.FONT_TITLE)
            dpg.add_spacer(width=-1)
            dpg.add_button(label="unprotected", tag=t["state_pill"],
                           width=112, height=24)
            _make_pill_themes()

        # power ring + the tunnel info beside it
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_spacer(width=4)
            _build_ring()
            dpg.add_spacer(width=12)
            with dpg.group():
                dpg.add_spacer(height=14)
                dpg.add_text("CEEN TUNNEL", tag=t["proto_txt"],
                             color=c("muted"))
                dpg.bind_item_font(dpg.last_item(), theme.FONT_SMALL)
                dpg.add_spacer(height=4)
                dpg.add_button(label="DISCONNECTED", tag=t["proto_pill"],
                               width=112, height=22)
                theme.style_button(t["proto_pill"], color=c("panel"))
                dpg.add_spacer(height=6)
                app.spark = Sparkline(136, 26)
                app.spark.build()

        # where am I connected?
        dpg.add_spacer(height=4)
        dpg.add_text("Not Connected", tag=t["loc_name"])
        dpg.bind_item_font(dpg.last_item(), theme.FONT_TITLE)
        with dpg.group(horizontal=True):
            dpg.add_text("Network >", tag=t["net_lbl"], color=c("muted"))
            dpg.bind_item_font(dpg.last_item(), theme.FONT_SMALL)
            dpg.add_text("", tag=t["exit_ip"], color=c("text"))

        # server list header + the list itself (its own scroll pane)
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_text("ALL LOCATIONS")
            dpg.bind_item_font(dpg.last_item(), theme.FONT_SMALL)
            dpg.add_text("|", color=c("faint"))
            dpg.add_text("0", tag=t["loc_count"], color=c("muted"))
            dpg.bind_item_font(dpg.last_item(), theme.FONT_SMALL)
            dpg.add_text("tap a country to see its servers",
                         color=c("faint"))
            dpg.bind_item_font(dpg.last_item(), theme.FONT_SMALL)
        server_list.build(app)      # scrollable; shrinks to fit buttons

        # bottom actions — ALWAYS visible, no scrolling needed
        dpg.add_spacer(height=6)
        with dpg.group(horizontal=True):
            dpg.add_button(label="CONNECT FASTEST", tag=t["fast_btn"],
                           width=160, height=27,
                           callback=lambda: app.connect_fastest())
            theme.style_button(t["fast_btn"], solid=True)
            dpg.add_button(label="PROXY CHECKER", tag=t["backup_hint"],
                           width=160, height=27,
                           callback=lambda: app.ui_show_checker())
            theme.style_button(t["backup_hint"], color=c("panel"))

    theme.style_child(t["connect_root"], bg=c("bg"))
    _bind_power(app)                # real click handler on the ring


def _build_ring() -> None:
    """The drawlist: glow layers, gradient arc pieces, knob, power icon."""
    with dpg.drawlist(width=int(_C * 2), height=int(_C * 2), tag=_RING):
        # fake gaussian blur: three soft concentric circles
        dpg.draw_circle([_C, _C], 36, color=(0, 0, 0, 0), fill=(0, 0, 0, 0),
                        tag="glow_core")
        dpg.draw_circle([_C, _C], _R + 12, color=(0, 0, 0, 0), tag="glow_mid")
        dpg.draw_circle([_C, _C], _R + 22, color=(0, 0, 0, 0), tag="glow_out")
        # the gradient ring: N short arcs, alpha ramping around the circle
        for i in range(_SEG):
            dpg.draw_polyline([(1, 1), (1, 1)], thickness=5, tag=f"seg_{i}")
        # click ripples (3 max, expand + fade)
        for i in range(3):
            dpg.draw_circle([_C, _C], _R + 8, color=(0, 0, 0, 0), thickness=2,
                            tag=f"ripple_{i}")
            dpg.hide_item(f"ripple_{i}")
        # inner knob + the power symbol (circle with a gap + a bar)
        dpg.draw_circle([_C, _C], 31, color=(0, 0, 0, 0), fill=c("panel"),
                        tag="ring_knob")
        dpg.draw_polyline([(1, 1), (1, 1)], thickness=3, tag="icon_arc")
        dpg.draw_line([_C, _C - 6], [_C, _C + 8], color=c("muted"),
                      thickness=3, tag="icon_bar")


def _make_pill_themes() -> None:
    """One theme per status-pill state (built once, bound later)."""
    for state, col, txt in (("off", c("panel"), c("muted")),
                            ("connecting", c("amber"), c("black")),
                            ("on", c("green_dn"), c("white"))):
        with dpg.theme(tag=f"pill_theme_{state}"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, col)
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                    theme.blend_rgb(col, c("white"), 0.12))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, col)
                dpg.add_theme_color(dpg.mvThemeCol_Text, txt)
    # the red theme for the DISCONNECT/CANCEL state of the action button
    with dpg.theme(tag="btn_red"):
        with dpg.theme_component(dpg.mvButton):
            dpg.add_theme_color(dpg.mvThemeCol_Button, c("red"))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered,
                                theme.blend_rgb(c("red"), c("black"), 0.25))
            dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, c("red"))
            dpg.add_theme_color(dpg.mvThemeCol_Text, c("white"))


def update_action_button(app) -> None:
    """The bottom-left button is ALWAYS the obvious action:
        off        -> CONNECT FASTEST (blue)
        connecting -> CANCEL         (red)
        connected  -> DISCONNECT     (red)
    This is the unmissable off-switch (the ring stays a toggle too)."""
    mode = "on" if app.connected else ("busy" if app.connecting else "off")
    if getattr(app, "_action_mode", None) == mode:
        return                       # nothing changed this frame
    app._action_mode = mode
    t = app.tags
    if mode == "on":
        dpg.configure_item(t["fast_btn"], label="DISCONNECT")
        dpg.set_item_callback(t["fast_btn"], lambda *a: app._disconnect())
        dpg.bind_item_theme(t["fast_btn"], "btn_red")
    elif mode == "busy":
        dpg.configure_item(t["fast_btn"], label="CANCEL")
        dpg.set_item_callback(t["fast_btn"], lambda *a: app.cancel_connect())
        dpg.bind_item_theme(t["fast_btn"], "btn_red")
    else:
        dpg.configure_item(t["fast_btn"], label="CONNECT FASTEST")
        dpg.set_item_callback(t["fast_btn"],
                              lambda *a: app.connect_fastest())
        dpg.bind_item_theme(t["fast_btn"], f"btn_theme_{t['fast_btn']}")


# ── interaction ──────────────────────────────────────────────────────────
def _bind_power(app) -> None:
    """Invisible button that sits exactly ON the ring: tap = toggle.

    It is absolutely positioned onto the ring's measured spot every
    frame (see place_power_hit), so it can never drift out of place.
    """
    app._ripples = []
    app._press_ts = 0.0

    def on_power() -> None:
        app._press_ts = time.monotonic()
        if len(app._ripples) < 3:
            app._ripples.append(time.monotonic())
        app.toggle()

    dpg.add_button(label="", width=int(_C * 2), height=int(_C * 2),
                   tag="power_hit", callback=on_power, show=False)
    theme.style_button("power_hit", color=(0, 0, 0, 0))


def _pos_in_window(tag: str, root_tag: str) -> tuple:
    """An item's absolute offset inside a child window: the position of
    every container between it and the window, added up."""
    x = y = 0
    cur = tag
    for _ in range(6):
        if cur == root_tag or cur is None:
            break
        try:
            px, py = dpg.get_item_pos(cur)
        except Exception:  # noqa: BLE001 — not laid out yet
            break
        x += px
        y += py
        cur = dpg.get_item_parent(cur)
    return x, y


def place_power_hit(app) -> None:
    """Keep the invisible hit-button exactly on the ring (cheap per-frame
    assert: re-aims if the layout ever shifts, e.g. after a resize)."""
    if not dpg.does_item_exist("power_hit"):
        return
    try:
        x, y = _pos_in_window(_RING, app.tags["connect_root"])
        if x == 0 and y == 0:      # layout not measured yet
            return
        cur = dpg.get_item_pos("power_hit")
        if list(cur) != [x, y]:
            dpg.configure_item("power_hit", pos=[x, y], show=True)
        elif not dpg.is_item_shown("power_hit"):
            dpg.show_item("power_hit")
    except Exception:  # noqa: BLE001 — try again next frame
        pass


def set_ring_mode(app, mode: str) -> None:
    """Ring + pills switch state; colors animate in set_ring_frame()."""
    if getattr(app, "_ring_mode", None) == mode:
        return
    app._ring_mode = mode
    t = app.tags
    dpg.bind_item_theme(t["state_pill"], f"pill_theme_{mode}")
    # buttons show their LABEL: only configure_item(label=...) changes it
    dpg.configure_item(t["state_pill"], label={
        "off": "unprotected", "connecting": "connecting...",
        "on": "protected"}[mode])
    dpg.configure_item(t["proto_pill"], label={
        "off": "DISCONNECTED", "connecting": "NEGOTIATING",
        "on": "ENCRYPTED"}[mode])


# ── per-frame animation ──────────────────────────────────────────────────
# mood per state: (ring color, orbit speed deg/s, alpha low/high, glow)
_MOOD = {
    "off":        ((86, 96, 118), 14.0, 0.10, 0.45, 0.0),
    "connecting": (c("amber"), 320.0, 0.35, 1.00, 0.9),
    "on":         (c("green"), 32.0, 0.55, 1.00, 0.55),
}


def set_ring_frame(app, dt: float) -> None:
    """Everything that moves on the ring, once per frame."""
    mode = getattr(app, "_ring_mode", "off")
    col, speed, a_lo, a_hi, glow = _MOOD[mode]
    t0 = time.monotonic()
    breathe = (0.5 + 0.5 * math.sin(t0 * 5.0)) if mode == "connecting" \
        else (0.5 + 0.5 * math.sin(t0 * 2.0))
    alpha_scale = 1.0 if mode != "connecting" else 0.65 + 0.35 * breathe

    # ── orbiting gradient ring ────────────────────────────────────────
    app._orbit = (getattr(app, "_orbit", 0.0) + speed * dt) % 360.0
    for i in range(_SEG):
        a0 = app._orbit + i * (360.0 / _SEG)
        pts = _arc_points(_C, _C, _R, a0, 360.0 / _SEG * 0.62, 4)
        ramp = a_lo + (a_hi - a_lo) * (i / (_SEG - 1))
        alpha = int(255 * ramp * alpha_scale)
        dpg.configure_item(f"seg_{i}", points=pts, color=col + (alpha,))

    # ── layered glow behind everything ────────────────────────────────
    g = glow * (0.8 + 0.2 * breathe)
    dpg.configure_item("glow_core", radius=36, fill=col + (int(26 * g),))
    dpg.configure_item("glow_mid", radius=(_R + 12) * (1.0 + 0.03 * breathe),
                       color=col + (int(70 * g),), thickness=3)
    dpg.configure_item("glow_out", radius=(_R + 22) * (1.0 + 0.05 * breathe),
                       color=col + (int(30 * g),), thickness=2)

    # ── knob + power icon (press makes it sink briefly) ───────────────
    press = max(0.0, 1.0 - (t0 - getattr(app, "_press_ts", 0.0)) / 0.22)
    knob_r = 31 - round(2 * press) + \
        (round(2 * breathe) if mode == "connecting" else 0)
    dpg.configure_item("ring_knob", radius=knob_r,
                       fill=theme.blend_rgb(c("panel"), col, 0.10 * g))
    icon_col = theme.blend_rgb(c("muted"), col, max(g, 0.55))
    dpg.configure_item("icon_arc",
                       points=_arc_points(_C, _C, 16, -65, 310, 14),
                       color=icon_col)
    dpg.configure_item("icon_bar", color=icon_col)

    # ── click ripples: expand + fade ──────────────────────────────────
    live = list(getattr(app, "_ripples", []))
    for i in range(3):
        if i < len(live):
            f = (t0 - live[i]) / 0.55
            if f < 1.0:
                dpg.show_item(f"ripple_{i}")
                dpg.configure_item(f"ripple_{i}", radius=_R + 8 + f * 20,
                                   color=col + (int(150 * (1 - f)),))
                continue
        dpg.hide_item(f"ripple_{i}")
    app._ripples = [r for r in live if t0 - r < 0.55]


def _arc_points(cx: float, cy: float, r: float, start_deg: float,
                sweep_deg: float, n: int = 8) -> list:
    """Points along a circle arc (start_deg 0 = 12 o'clock)."""
    pts = []
    for i in range(n + 1):
        a = math.radians(start_deg + sweep_deg * i / n - 90)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


# ── data-driven text updates ─────────────────────────────────────────────
def set_location_line(app, name: str) -> None:
    """The big location line under the ring."""
    dpg.set_value(app.tags["loc_name"], name)


def set_exit_ip(app, ip: str) -> None:
    """The 'Network > 98.14.44.215 · direct' row."""
    dpg.set_value(app.tags["exit_ip"], ip or "not protected")
