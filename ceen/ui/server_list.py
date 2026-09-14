"""The server list — countries, expandable down to SINGLE servers.

Tap a country row: it expands to show up to 4 of its fastest servers
(tap again to collapse). Tap a server row: Ceen connects through THAT
exact server. Everything is painted into a fixed pool of row widgets
(no rows created/destroyed at runtime — the UI stays silky).
"""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ceen.ui import theme
from ceen.ui.theme import c
from ceen.utils.textutil import flag_emoji

ROWS = 44                # fixed row widgets in the pool
_SERVERS_SHOWN = 4       # servers listed when a country is expanded


def build(app) -> None:
    """Create the list pane + the fixed rows (call once at startup)."""
    with dpg.child_window(tag="locations", height=-1, border=False):
        with dpg.theme(tag="slim_scrollbar"):
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 6)
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg, (0, 0, 0, 0))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,
                                    (70, 76, 90, 140))
                dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrabHovered,
                                    (90, 96, 110, 190))
        dpg.bind_item_theme("locations", "slim_scrollbar")
        dpg.add_text("scanning for servers...", tag="loc_empty",
                     color=c("faint"))
        with dpg.theme(tag="row_normal"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, (0, 0, 0, 0))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, c("panel_hi"))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, c("panel_hi"))
                dpg.add_theme_color(dpg.mvThemeCol_Text, c("text"))
        with dpg.theme(tag="chip_grey"):
            with dpg.theme_component(dpg.mvButton):
                dpg.add_theme_color(dpg.mvThemeCol_Button, c("panel_hi"))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, c("border"))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonActive, c("panel_hi"))
                dpg.add_theme_color(dpg.mvThemeCol_Text, c("text"))
        app.list_rows = []
        for i in range(ROWS):
            rt = f"loc_row_{i}"
            with dpg.group(tag=rt, horizontal=True, show=False):
                dpg.add_button(label="--", tag=f"{rt}_flag", width=36,
                               height=20, user_data=None)
                dpg.add_spacer(width=6)
                dpg.add_button(label="", tag=f"{rt}_name", width=180,
                               height=22, user_data=None)
                dpg.add_button(label="", tag=f"{rt}_ms", width=96,
                               height=22, user_data=None)
            app.list_rows.append(rt)
            dpg.bind_item_theme(f"{rt}_flag", "chip_grey")
            for sub in (f"{rt}_name", f"{rt}_ms"):
                dpg.bind_item_theme(sub, "row_normal")


def refresh(app) -> None:
    """Paint countries (and the expanded one's servers) into the pool."""
    t = app.tags
    n = sum(len(s) for _n, _cc, s in app.groups)
    dpg.set_value(t["loc_count"], str(n))
    dpg.configure_item("loc_empty", show=not app.groups)

    # flatten: (kind, data...) — countries, expanded servers, a "+more"
    slots = []
    for name, cc, servers in app.groups:
        slots.append(("country", name, cc, servers))
        if app.expanded == name:
            for e in servers[:_SERVERS_SHOWN]:
                slots.append(("server", e))
            if len(servers) > _SERVERS_SHOWN:
                slots.append(("more", len(servers) - _SERVERS_SHOWN, name))

    for i, rt in enumerate(app.list_rows):
        show = i < len(slots)
        dpg.configure_item(rt, show=show)
        if not show:
            continue
        kind = slots[i][0]
        if kind == "country":
            _paint_country(rt, slots[i][1], slots[i][2], slots[i][3], app)
        elif kind == "server":
            _paint_server(rt, slots[i][1], app)
        else:
            _paint_more(rt, slots[i][1], slots[i][2], app)


def _paint_country(rt: str, name: str, cc: str, servers: list, app) -> None:
    """A country row: badge, name, 'n · fastest-ping'."""
    best = servers[0]
    arrow = "v " if app.expanded == name else "> "      # ascii, always renders
    dpg.configure_item(f"{rt}_flag", label=flag_emoji(cc))
    dpg.configure_item(f"{rt}_name", label=f" {arrow}{name[:20]}")
    dpg.configure_item(f"{rt}_ms",
                       label=f"{len(servers)} · {best.latency or '?'}ms  ")
    for sub in (f"{rt}_flag", f"{rt}_name", f"{rt}_ms"):
        dpg.set_item_callback(sub, lambda s, d, n=name: app.toggle_expand(n))
        dpg.set_item_user_data(sub, name)


def _paint_server(rt: str, e, app) -> None:
    """A single server row: '·', ip:port, its ping — tap to use it."""
    active = app.connected and e.exit_ip and e.exit_ip == app.exit_ip
    dpg.configure_item(f"{rt}_flag", label=">")
    dpg.configure_item(f"{rt}_name",
                       label=f"  {'*' if active else ' '}{e.host}")
    dpg.configure_item(f"{rt}_ms", label=f"{e.latency or '?'}ms  ")
    for sub in (f"{rt}_flag", f"{rt}_name", f"{rt}_ms"):
        dpg.set_item_callback(sub, lambda s, d, entry=e: app.connect_server(entry))
        dpg.set_item_user_data(sub, e)


def _paint_more(rt: str, extra: int, name: str, app) -> None:
    """A '+N more' row — tapping just keeps the country open."""
    dpg.configure_item(f"{rt}_flag", label="++")
    dpg.configure_item(f"{rt}_name", label=f"  +{extra} more")
    dpg.configure_item(f"{rt}_ms", label="")
    for sub in (f"{rt}_flag", f"{rt}_name", f"{rt}_ms"):
        dpg.set_item_callback(sub, lambda s, d, n=name: app.toggle_expand(n))
        dpg.set_item_user_data(sub, name)
