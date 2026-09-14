"""Dear PyGui bootstrap: viewport, fonts, theme, and the run loop.

Dear PyGui is immediate-mode and GPU-rendered, which is why the window
feels faster than the old tkinter one: nothing is re-laid-out, every
frame is just drawn. This module owns the "when" (one render loop) and
hands each frame to app.update().
"""

from __future__ import annotations

import os
import tempfile

import dearpygui.dearpygui as dpg

from ceen.config import APP_NAME
from ceen.ui import theme


class Ui:
    """Owns the dpg context: window creation, fonts, per-frame dispatch."""

    def __init__(self, app, width: int = None, height: int = None) -> None:
        self.app = app
        # remember the window size the user chose last time
        from ceen.utils.settings import current_size
        saved = current_size(app.settings)
        width = width or (saved[0] if saved else 380)
        height = height or (saved[1] if saved else 590)
        dpg.create_context()
        theme.setup_fonts()
        theme.setup_theme()
        # brand icon for the title bar + taskbar (generated, cached in tmp)
        icon_path = os.path.join(tempfile.gettempdir(), "ceen_icon.ico")
        try:
            if not os.path.exists(icon_path):
                from ceen.ui.icon import save_ico
                save_ico(icon_path, 32)
        except Exception:  # noqa: BLE001 — icon is cosmetic
            icon_path = ""
        dpg.create_viewport(title=APP_NAME, width=width,
                            height=height, resizable=True,
                            min_width=340, min_height=520,
                            decorated=False,        # no white OS frame
                            small_icon=icon_path, large_icon=icon_path)
        with dpg.window(tag="main", no_title_bar=True, no_move=False,
                        no_scrollbar=True):
            from ceen.ui.titlebar import add_title_bar
            add_title_bar()                  # our OWN dark bar, always
            from ceen.ui.panel_connect import build_connect_panel
            from ceen.ui.panel_checker import build_checker_panel
            build_connect_panel(app)
            build_checker_panel(app)
        dpg.set_viewport_resize_callback(self._on_resize)
        self._last_size = (width, height)
        dpg.set_primary_window("main", True)

    def _on_resize(self) -> None:
        """Remember the window size the user chose (saved on exit)."""
        try:
            self._last_size = (dpg.get_viewport_client_width(),
                               dpg.get_viewport_client_height())
        except Exception:  # noqa: BLE001 — during shutdown dpg may be gone
            pass

    @property
    def size(self) -> tuple:
        return self._last_size

    def run(self, vsync: bool = True) -> None:
        """The render loop — calls app.update() every frame.

        Modern dpg order: setup_dearpygui() -> show_viewport() -> loop.
        On the way out (window closed OR crash) the app's shutdown()
        always restores the user's internet settings.
        """
        dpg.setup_dearpygui()
        dpg.show_viewport()
        try:
            while dpg.is_dearpygui_running():
                self.app.update()
                dpg.render_dearpygui_frame()
                # one frame exists now: widget positions are measurable
                self.app._frames = getattr(self.app, "_frames", 0) + 1
        finally:
            # runs on clean exit AND on exceptions (crash safety)
            try:
                w, h = self._last_size
                self.app.save_settings(win_w=w, win_h=h)
            except Exception:  # noqa: BLE001 — saving size is cosmetic
                pass
            self.app.shutdown()
            dpg.destroy_context()

    def primary_monitor_center(self) -> None:
        """Center the small window on screen on first launch."""
        try:
            import tkinter as tk
            r = tk.Tk()
            r.withdraw()
            w, h = self._last_size
            x = (r.winfo_screenwidth() - w) // 2
            y = (r.winfo_screenheight() - h) // 3
            r.destroy()
            dpg.set_viewport_pos([max(0, x), max(0, y)])
        except Exception:  # noqa: BLE001 — centering is cosmetic
            pass
