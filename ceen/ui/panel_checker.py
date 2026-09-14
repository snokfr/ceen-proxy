"""The CHECKER screen — where the list gets tested (second page).

The table is a REAL Dear PyGui table, but its rows are created ONCE
(fixed pool) and only the cell text is updated afterwards. Deleting and
re-creating hundreds of rows every frame used to starve the renderer
and leave this page looking frozen — that is engineered out now.
Search + alive filter simply change which entries are painted in.
"""

from __future__ import annotations

import dearpygui.dearpygui as dpg

from ceen.ui import theme
from ceen.ui.theme import c
from ceen.utils.textutil import flag_emoji, latency_color

_ROWS = 60                      # fixed row widgets (scroll for the rest)


def build_checker_panel(app) -> None:
    """Create every widget of the Checker screen."""
    t = app.tags
    with dpg.child_window(tag=t["checker_root"], show=False, border=False):
        # top row: BACK to the main screen + filters
        with dpg.group(horizontal=True):
            dpg.add_button(label="< BACK", tag="checker_back", width=68,
                           height=24, callback=app.ui_show_connect)
            theme.style_button("checker_back", color=c("panel"))
            dpg.add_input_text(hint="search...", tag=t["search"], width=-60,
                               callback=app.ui_search)
            theme.style_input(t["search"])
            dpg.add_checkbox(label="alive", tag=t["alive_only"],
                             callback=app.ui_filter)
        # scan controls: start / stop / open the log + live alive-count
        with dpg.group(horizontal=True):
            dpg.add_button(label="START SCAN", tag=t["scan_btn"], width=92,
                           height=26, callback=app.ui_start_scan)
            theme.style_button(t["scan_btn"], solid=True)
            dpg.add_button(label="STOP", tag=t["stop_btn"], width=62,
                           height=26, callback=app.ui_stop_scan)
            theme.style_button(t["stop_btn"])
            dpg.add_button(label="LOG", tag=t["log_btn"], width=52,
                           height=26, callback=app.ui_open_log)
            theme.style_button(t["log_btn"])
            dpg.add_text("", tag=t["checker_status"], color=c("muted"))
            dpg.bind_item_font(dpg.last_item(), theme.FONT_SMALL)
        # progress bar with the 412/778 counter drawn on it
        dpg.add_progress_bar(tag=t["progress"], width=-1, height=6,
                             default_value=0.0, overlay="idle")
        # the results table: fixed rows, slim scrollbar, aligned columns
        with dpg.child_window(tag="table_area", height=-1, border=False):
            with dpg.theme(tag="slim_scrollbar2"):
                with dpg.theme_component(dpg.mvAll):
                    dpg.add_theme_style(dpg.mvStyleVar_ScrollbarSize, 6)
                    dpg.add_theme_color(dpg.mvThemeCol_ScrollbarBg,
                                        (0, 0, 0, 0))
                    dpg.add_theme_color(dpg.mvThemeCol_ScrollbarGrab,
                                        (70, 76, 90, 140))
            dpg.bind_item_theme("table_area", "slim_scrollbar2")
            with dpg.table(tag="results", header_row=True,
                           policy=dpg.mvTable_SizingStretchProp,
                           row_background=True, scrollY=True, height=-1):
                dpg.add_table_column(label="address", width_stretch=True)
                dpg.add_table_column(label="ping", width_fixed=True,
                                     init_width_or_weight=58)
                dpg.add_table_column(label="country", width_fixed=True,
                                     init_width_or_weight=118)
                dpg.add_table_column(label="status", width_fixed=True,
                                     init_width_or_weight=72)
                app.table_rows = []      # NOT app.rows: that belongs to
                for i in range(_ROWS):   # the connect panel's country list
                    rt = f"chk_row_{i}"
                    with dpg.table_row(tag=rt):
                        dpg.add_text("", tag=f"{rt}_addr")
                        dpg.add_text("", tag=f"{rt}_ping")
                        dpg.add_text("", tag=f"{rt}_cc")
                        dpg.add_text("", tag=f"{rt}_st")
                    app.table_rows.append(rt)
                    dpg.configure_item(rt, show=False)
        # bottom row: copy/export the alive list
        with dpg.group(horizontal=True):
            dpg.add_button(label="COPY ALIVE", tag=t["copy_btn"], width=88,
                           height=26, callback=app.ui_copy)
            theme.style_button(t["copy_btn"])
            dpg.add_button(label="EXPORT", tag=t["export_btn"], width=88,
                           height=26, callback=app.ui_export)
            theme.style_button(t["export_btn"])
    theme.style_child(t["checker_root"], bg=c("bg"))


# ── runtime updates (called from app.update()) ───────────────────────────────

def refresh_table(app) -> None:
    """Paint the visible entries into the FIXED rows (in place, cheap).

    Called at ~4fps; also updates the counter so the user always sees
    how the scan is doing at a glance.
    """
    rows = app.visible_rows()
    for i, rt in enumerate(app.table_rows):
        show = i < len(rows)
        dpg.configure_item(rt, show=show)
        if not show:
            continue
        e = rows[i]
        dpg.set_value(f"{rt}_addr", e.host[:26])
        dpg.set_value(f"{rt}_ping", f"{e.latency}ms" if e.latency else "-")
        dpg.configure_item(f"{rt}_ping", color=latency_color(e.latency))
        where = f"{flag_emoji(e.exit_cc)} {e.country or ''}" if e.exit_cc \
            else (e.country or "")
        dpg.set_value(f"{rt}_cc", where)
        if e.alive:
            dpg.set_value(f"{rt}_st", "alive")
            dpg.configure_item(f"{rt}_st", color=c("green"))
        else:
            dpg.set_value(f"{rt}_st", (e.error or "dead")[:11])
            dpg.configure_item(f"{rt}_st", color=c("faint"))


def set_progress(app, done: int, total: int, active: bool) -> None:
    """The slim progress bar + alive counter + button states."""
    t = app.tags
    frac = done / total if total else 0.0
    alive = sum(1 for e in app.entries if e.alive)
    dpg.configure_item(t["progress"], default_value=frac,
                       overlay=f"{done}/{total}" if total else "idle")
    dpg.configure_item(t["scan_btn"], enabled=not active)
    dpg.configure_item(t["stop_btn"], enabled=active)
    dpg.set_value(t["checker_status"], f"{alive} alive" if total else "")


def set_status(app, text: str) -> None:
    dpg.set_value(app.tags["checker_status"], text)


def open_log_window(app, lines) -> None:
    """A small window showing this session's log lines."""
    with dpg.window(popup=True, title="session log", width=720, height=420,
                    tag="log_win", on_close=lambda: dpg.delete_item("log_win")):
        dpg.add_text("this session's full log (also saved in logs/):",
                     color=c("muted"))
        dpg.add_separator()
        with dpg.child_window(border=False, height=-1):
            for _lvl, line in lines[-600:]:
                col = c("red") if " ERROR" in line else \
                    (c("amber") if " WARNING" in line else c("muted"))
                dpg.add_text(line, color=col)
