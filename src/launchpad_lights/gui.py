"""Settings window: live LED preview (clickable), mode switching and per-mode settings in tabs.

Tk runs on the main thread, the render loop on its own thread, the tray on pystray's thread.
The window only talks to the app through its thread-safe methods (post, set_config, ...).
"""
import copy
import logging
import os
import queue
import signal
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from PIL import ImageTk

from launchpad_lights import autostart
from launchpad_lights.config import app_dir
from launchpad_lights.launchpad.events import ButtonEvent
from launchpad_lights.launchpad.frame import OFF, SIDE, TOP, Color
from launchpad_lights.modes import registry
from launchpad_lights.modes.clock import POMODORO, VIEW_LABELS as CLOCK_VIEWS
from launchpad_lights.modes.macro_pad import ACTIONS, COLOURS, PAGES, run_action
from launchpad_lights.modes.visualiser import SUB_MODE_LABELS
from launchpad_lights.services.analysis import GAIN_DEFAULTS, SENSITIVITY
from launchpad_lights.winutil import MEDIA_KEYS, audio_apps

from .tray import TITLE, Tray, make_icon, mode_label

log = logging.getLogger(__name__)

CELL = 34
GAP = 6
RED_LEVELS = (0, 140, 200, 255)
GREEN_LEVELS = (0, 130, 190, 235)
PREVIEW_BG = "#161616"
OFF_FILL = "#2c2c2c"
PREVIEW_MS = 40
STATE_MS = 300
SYSTEM_SOURCE = "System (all apps)"
NO_MODE = "(none)"
NO_ACTION = "(none)"

SLIDERS = [  # key, label, from, to, format
    ("gain_db", "Gain", -12, 24, "{:+.0f} dB"),
    ("range_db", "Range", 12, 48, "{:.0f} dB"),
    ("noise_floor_db", "Noise gate", -100, -40, "{:.0f} dB"),
]
VALUE_HINTS = {
    "media": "One of: " + ", ".join(MEDIA_KEYS),
    "key": "Key combo, e.g. ctrl+shift+m, win+d, f13, alt+tab",
    "run": "Command line, e.g. notepad.exe or \"C:\\Tools\\vpn.bat\" connect",
    "url": "URL or file to open, e.g. https://example.com",
    "mic_mute": "No value needed. Lit red when muted, green when live",
}


def led_fill(c: Color) -> str:
    if c == OFF:
        return OFF_FILL
    r, g = c
    return f"#{RED_LEVELS[r]:02x}{GREEN_LEVELS[g]:02x}00"


def led_event(index: int, pressed: bool) -> ButtonEvent:
    if index < SIDE:
        y, x = divmod(index, 8)
        return ButtonEvent("pad", index, pressed, x, y)
    if index < TOP:
        return ButtonEvent("side", index - SIDE, pressed)
    return ButtonEvent("top", index - TOP, pressed)


class MainWindow:
    def __init__(self, root: tk.Tk, app, ui: queue.Queue, worker: threading.Thread):
        self.root, self.app, self.ui, self.worker = root, app, ui, worker
        self.cfg = app.config
        self.viz = app.config.section("visualiser")
        self.tray: Tray | None = None
        self._told_about_tray = False
        self._pressed: int | None = None
        self._shown: list[Color] = []
        self._slots_shown: list[str] = []

        root.title(TITLE)
        root.resizable(False, False)
        self._icon = ImageTk.PhotoImage(make_icon(64))
        root.iconphoto(True, self._icon)
        root.protocol("WM_DELETE_WINDOW", self.hide)

        outer = ttk.Frame(root, padding=12)
        outer.grid(sticky="nsew")
        self.status = ttk.Label(outer, foreground="#666")
        self.status.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        left = ttk.Frame(outer)
        left.grid(row=1, column=0, sticky="n", padx=(0, 14))
        self._build_preview(left).pack()
        self.mode_box = ttk.LabelFrame(left, text="Mode", padding=8)
        self.mode_box.pack(fill="x", pady=(10, 0))
        self.mode_var = tk.StringVar()
        self.standby_var = tk.BooleanVar()
        self._rebuild_modes()

        tabs = ttk.Notebook(outer)
        tabs.grid(row=1, column=1, sticky="nsew")
        for title, build in [("Visualiser", self._tab_visualiser), ("Audio", self._tab_audio),
                             ("Macro pad", self._tab_macro), ("Clock", self._tab_clock),
                             ("Top buttons", self._tab_top), ("General", self._tab_general)]:
            frame = ttk.Frame(tabs, padding=10)
            build(frame)
            tabs.add(frame, text=title)

        buttons = ttk.Frame(outer)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Hide to tray", command=self.hide).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Quit", command=self.quit).pack(side="left")

        # First ticks run inside mainloop, never during construction.
        root.after(0, self._tick_preview)
        root.after(0, self._tick_state)

    # Helpers

    def _set(self, section: str, **values) -> None:
        self.app.set_config(section, **values)

    def _spinbox(self, parent, section: str, key: str, lo: float, hi: float, step: float, width: int = 5):
        var = tk.StringVar(value=str(self.cfg.section(section).get(key, lo)))

        def commit(*_):
            try:
                value = min(max(float(var.get()), lo), hi)
            except ValueError:
                return
            value = int(value) if float(step).is_integer() else value
            if self.cfg.section(section).get(key) != value:
                self._set(section, **{key: value})

        box = ttk.Spinbox(parent, from_=lo, to=hi, increment=step, textvariable=var, width=width, command=commit)
        box.bind("<Return>", commit)
        box.bind("<FocusOut>", commit)
        return box

    # Left column

    def _build_preview(self, parent) -> tk.Canvas:
        size = 9 * CELL + GAP
        c = self.canvas = tk.Canvas(parent, width=size, height=size, bg=PREVIEW_BG, highlightthickness=0)
        self.items: list[int] = [0] * 80
        inset = 3
        for i in range(80):
            if i < SIDE:
                row, col = divmod(i, 8)
                x, y = col * CELL, (row + 1) * CELL + GAP
                item = c.create_rectangle(x + inset, y + inset, x + CELL - inset, y + CELL - inset,
                                          fill=OFF_FILL, outline="")
            else:
                if i < TOP:
                    x, y = 8 * CELL + GAP, (i - SIDE + 1) * CELL + GAP
                else:
                    x, y = (i - TOP) * CELL, 0
                item = c.create_oval(x + 7, y + 7, x + CELL - 7, y + CELL - 7, fill=OFF_FILL, outline="")
            c.tag_bind(item, "<ButtonPress-1>", lambda e, i=i: self._press(i))
            self.items[i] = item
        c.bind("<ButtonRelease-1>", lambda e: self._release())
        return c

    def _rebuild_modes(self) -> None:
        for child in self.mode_box.winfo_children():
            child.destroy()
        self._slots_shown = list(self.app.slots)
        for i, name in enumerate(self.app.slots):
            if name:
                ttk.Radiobutton(self.mode_box, text=f"{i + 1}   {mode_label(name)}", value=name,
                                variable=self.mode_var, command=self._switch_mode).pack(anchor="w")
        ttk.Checkbutton(self.mode_box, text="Standby (all LEDs off)", variable=self.standby_var,
                        command=lambda: self.app.set_standby(self.standby_var.get())).pack(anchor="w", pady=(6, 0))

    # Tabs

    def _tab_visualiser(self, tab) -> None:
        box = ttk.LabelFrame(tab, text="View", padding=8)
        box.pack(fill="x")
        self.view_var = tk.IntVar()
        for i, label in enumerate(SUB_MODE_LABELS):
            ttk.Radiobutton(box, text=label, value=i + 1, variable=self.view_var,
                            command=lambda: self._set("visualiser", sub_mode=self.view_var.get())
                            ).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 16))

        cyc = ttk.LabelFrame(tab, text="Auto-cycle", padding=8)
        cyc.pack(fill="x", pady=(10, 0))
        self.cycle_var = tk.BooleanVar()
        ttk.Checkbutton(cyc, text="Switch to a random view automatically", variable=self.cycle_var,
                        command=lambda: self._set("visualiser", auto_cycle=self.cycle_var.get())
                        ).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(cyc, text="Every").grid(row=1, column=0, sticky="w", pady=(6, 0))
        self._spinbox(cyc, "visualiser", "cycle_beats", 4, 256, 4).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(cyc, text="beats").grid(row=1, column=2, sticky="w", padx=(4, 0), pady=(6, 0))
        ttk.Label(cyc, text="or every").grid(row=2, column=0, sticky="w", pady=(4, 0))
        self._spinbox(cyc, "visualiser", "cycle_seconds", 5, 600, 5).grid(row=2, column=1, sticky="w", pady=(4, 0))
        ttk.Label(cyc, text="seconds when there's no clear beat").grid(row=2, column=2, sticky="w", padx=(4, 0),
                                                                       pady=(4, 0))
        self.bpm_label = ttk.Label(tab, font=("Segoe UI", 16, "bold"))
        self.bpm_label.pack(anchor="w", pady=(10, 0))

    def _tab_audio(self, tab) -> None:
        src = ttk.LabelFrame(tab, text="Capture from", padding=8)
        src.pack(fill="x")
        self.source_var = tk.StringVar()
        self.source_box = ttk.Combobox(src, textvariable=self.source_var, width=32)
        self.source_box.grid(row=0, column=0, sticky="w")
        self.source_box.bind("<<ComboboxSelected>>", lambda e: self._set_source())
        self.source_box.bind("<Return>", lambda e: self._set_source())
        ttk.Button(src, text="Refresh", command=self._refresh_sources).grid(row=0, column=1, padx=(6, 0))
        ttk.Label(src, foreground="#777", wraplength=330, justify="left", text=(
            "Pick an app to visualise only its audio (Windows 10 2004 or later). "
            "The list shows apps that are making sound; you can also type an .exe name.")
                  ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._refresh_sources()

        box = ttk.LabelFrame(tab, text="Gain", padding=8)
        box.pack(fill="x", pady=(10, 0))
        box.columnconfigure(1, weight=1)
        self.auto_var = tk.BooleanVar(value=bool(self.viz.get("auto_gain", True)))
        ttk.Checkbutton(box, text="Auto gain (follows the volume)", variable=self.auto_var,
                        command=self._set_auto).grid(row=0, column=0, columnspan=3, sticky="w")
        speed = ttk.Frame(box)
        speed.grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 6))
        ttk.Label(speed, text="Speed").pack(side="left", padx=(0, 8))
        self.speed_var = tk.StringVar()
        self.speed_buttons = [
            ttk.Radiobutton(speed, text=s.capitalize(), value=s, variable=self.speed_var,
                            command=lambda: self._set("visualiser", sensitivity=self.speed_var.get()))
            for s in SENSITIVITY
        ]
        for b in self.speed_buttons:
            b.pack(side="left", padx=(0, 6))

        self.slider_vars: dict[str, tk.DoubleVar] = {}
        self.slider_labels: dict[str, ttk.Label] = {}
        for row, (key, label, lo, hi, fmt) in enumerate(SLIDERS, start=2):
            ttk.Label(box, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8))
            var = tk.DoubleVar(value=float(self.viz.get(key, GAIN_DEFAULTS[key])))
            value_label = ttk.Label(box, width=8, anchor="e")
            ttk.Scale(box, from_=lo, to=hi, variable=var, length=200,
                      command=lambda v, k=key: self._slide(k)).grid(row=row, column=1, sticky="ew")
            value_label.grid(row=row, column=2, sticky="e")
            self.slider_vars[key], self.slider_labels[key] = var, value_label
            self._show_slider(key)
        ttk.Label(box, foreground="#777", wraplength=330, justify="left", text=(
            "Gain lifts or drops the bars. Range is how far below the loudest sound a pad still lights: "
            "lower is punchier. Noise gate keeps hiss dark.")).grid(row=5, column=0, columnspan=3, sticky="w",
                                                                    pady=(6, 0))
        ttk.Button(box, text="Reset to defaults", command=self._reset_gain).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(8, 0))
        self._update_speed_state()

    def _tab_macro(self, tab) -> None:
        self.macro_cfg = self.cfg.section("macro_pad")
        self.macros: list[dict] = copy.deepcopy(self.macro_cfg.get("buttons", []))
        self.macro_sel: tuple[int, int] | None = None

        top = ttk.Frame(tab)
        top.pack(fill="x")
        ttk.Label(top, text="Page").pack(side="left")
        self.page_var = tk.IntVar(value=1)
        ttk.Spinbox(top, from_=1, to=PAGES, textvariable=self.page_var, width=3, state="readonly",
                    command=self._draw_macro_grid).pack(side="left", padx=(6, 0))
        ttk.Label(top, text="  Side buttons 1-8 switch pages on the device", foreground="#777").pack(side="left")

        grid = ttk.Frame(tab)
        grid.pack(pady=(8, 8))
        self.macro_cells: list[tk.Button] = []
        for i in range(64):
            y, x = divmod(i, 8)
            b = tk.Button(grid, width=6, height=1, font=("Segoe UI", 7), relief="raised", bd=1,
                          command=lambda x=x, y=y: self._select_macro(x, y))
            b.grid(row=y, column=x, padx=1, pady=1)
            self.macro_cells.append(b)

        form = ttk.Frame(tab)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.macro_title = ttk.Label(form, text="Click a pad to edit it", font=("Segoe UI", 9, "bold"))
        self.macro_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.m_label, self.m_action, self.m_value, self.m_colour = (tk.StringVar() for _ in range(4))
        ttk.Label(form, text="Label").grid(row=1, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.m_label).grid(row=1, column=1, sticky="ew", pady=1)
        ttk.Label(form, text="Action").grid(row=2, column=0, sticky="w")
        action_box = ttk.Combobox(form, textvariable=self.m_action, values=[NO_ACTION, *ACTIONS], state="readonly")
        action_box.grid(row=2, column=1, sticky="ew", pady=1)
        action_box.bind("<<ComboboxSelected>>", lambda e: self._action_changed())
        ttk.Label(form, text="Value").grid(row=3, column=0, sticky="w")
        self.m_value_box = ttk.Combobox(form, textvariable=self.m_value)
        self.m_value_box.grid(row=3, column=1, sticky="ew", pady=1)
        self.m_hint = ttk.Label(form, foreground="#777", wraplength=330)
        self.m_hint.grid(row=4, column=1, sticky="w")
        ttk.Label(form, text="Colour").grid(row=5, column=0, sticky="w")
        ttk.Combobox(form, textvariable=self.m_colour, values=list(COLOURS), state="readonly").grid(
            row=5, column=1, sticky="ew", pady=1)
        actions = ttk.Frame(form)
        actions.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(actions, text="Save", command=self._save_macro).pack(side="left")
        ttk.Button(actions, text="Test", command=self._test_macro).pack(side="left", padx=6)
        ttk.Button(actions, text="Clear", command=self._clear_macro).pack(side="left")
        self._draw_macro_grid()

    def _tab_clock(self, tab) -> None:
        clock = self.cfg.section("clock")
        if POMODORO.total == 0:
            POMODORO.cfg = clock
            POMODORO.reset()
        box = ttk.LabelFrame(tab, text="View", padding=8)
        box.pack(fill="x")
        self.clock_view_var = tk.IntVar(value=int(clock.get("view", 1)))
        for i, label in enumerate(CLOCK_VIEWS):
            ttk.Radiobutton(box, text=label, value=i + 1, variable=self.clock_view_var,
                            command=lambda: self._set("clock", view=self.clock_view_var.get())).pack(anchor="w")
        self.h24_var = tk.BooleanVar(value=bool(clock.get("24h", True)))
        ttk.Checkbutton(box, text="24-hour time", variable=self.h24_var,
                        command=lambda: self._set("clock", **{"24h": self.h24_var.get()})).pack(anchor="w",
                                                                                                pady=(6, 0))
        pomo = ttk.LabelFrame(tab, text="Pomodoro", padding=8)
        pomo.pack(fill="x", pady=(10, 0))
        for row, (key, label) in enumerate([("work_minutes", "Work"), ("break_minutes", "Short break"),
                                            ("long_break_minutes", "Long break (every 4th)")]):
            ttk.Label(pomo, text=label).grid(row=row, column=0, sticky="w", pady=1)
            self._spinbox(pomo, "clock", key, 1, 180, 1).grid(row=row, column=1, sticky="w", padx=6)
            ttk.Label(pomo, text="min").grid(row=row, column=2, sticky="w")
        controls = ttk.Frame(pomo)
        controls.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(controls, text="Start / pause", command=lambda: self.app.post(POMODORO.toggle)).pack(side="left")
        ttk.Button(controls, text="Reset", command=lambda: self.app.post(POMODORO.reset)).pack(side="left", padx=6)
        self.pomo_label = ttk.Label(pomo, font=("Segoe UI", 16, "bold"))
        self.pomo_label.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(pomo, foreground="#777", wraplength=330, justify="left", text=(
            "On the device: side 3 shows the timer, any pad or side 6 starts/pauses, side 7 resets.")
                  ).grid(row=5, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _tab_top(self, tab) -> None:
        ttk.Label(tab, text="Choose which mode each round top button selects.", foreground="#777").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        names = registry.available()
        self._mode_by_label = {NO_MODE: "", **{mode_label(n): n for n in names}}
        self.slot_vars: list[tk.StringVar] = []
        for i in range(8):
            ttk.Label(tab, text=f"Button {i + 1}").grid(row=i + 1, column=0, sticky="w", padx=(0, 10), pady=2)
            var = tk.StringVar(value=mode_label(self.app.slots[i]) if self.app.slots[i] else NO_MODE)
            box = ttk.Combobox(tab, textvariable=var, values=list(self._mode_by_label), state="readonly", width=24)
            box.grid(row=i + 1, column=1, sticky="w", pady=2)
            box.bind("<<ComboboxSelected>>", lambda e: self._save_slots())
            self.slot_vars.append(var)
        ttk.Label(tab, foreground="#777", wraplength=330, justify="left", text=(
            "Holding button 8 for a second always toggles standby; a short press selects its mode.")
                  ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(10, 0))

    def _tab_general(self, tab) -> None:
        self.autostart_var = tk.BooleanVar(value=autostart.is_enabled())
        ttk.Checkbutton(tab, text="Start with Windows (in the tray)", variable=self.autostart_var,
                        command=self._toggle_autostart).pack(anchor="w")
        text = ttk.LabelFrame(tab, text="Scrolling text (clock, now playing)", padding=8)
        text.pack(fill="x", pady=(12, 0))
        self.text_size_var = tk.StringVar(value=self.cfg.section("app").get("text_size", "small"))
        for value, label in [("small", "Small: about 2 characters on screen at once"),
                             ("large", "Large: easier to read, about 1 character at once")]:
            ttk.Radiobutton(text, text=label, value=value, variable=self.text_size_var,
                            command=lambda: self._set("app", text_size=self.text_size_var.get())).pack(anchor="w")
        row = ttk.Frame(tab)
        row.pack(anchor="w", pady=(12, 0))
        ttk.Button(row, text="Open config folder", command=lambda: os.startfile(app_dir())).pack(side="left")
        ttk.Button(row, text="Open logs", command=lambda: os.startfile(app_dir() / "logs")).pack(side="left", padx=6)

    # Actions

    def _switch_mode(self) -> None:
        name = self.mode_var.get()
        self.app.post(lambda: self.app.switch(name))

    def _save_slots(self) -> None:
        self.app.set_slots([self._mode_by_label.get(v.get(), "") for v in self.slot_vars])

    def _toggle_autostart(self) -> None:
        try:
            autostart.set_enabled(self.autostart_var.get())
        except OSError as e:
            log.warning("Could not change start with Windows: %s", e)
            self.autostart_var.set(autostart.is_enabled())

    def _refresh_sources(self) -> None:
        current = self.viz.get("source", "") or SYSTEM_SOURCE
        apps = audio_apps()
        if current != SYSTEM_SOURCE and current not in apps:
            apps.append(current)
        self.source_box["values"] = [SYSTEM_SOURCE, *apps]
        self.source_var.set(current)

    def _set_source(self) -> None:
        value = self.source_var.get().strip()
        self._set("visualiser", source="" if value in ("", SYSTEM_SOURCE) else value)

    def _set_auto(self) -> None:
        self._set("visualiser", auto_gain=self.auto_var.get())
        self._update_speed_state()

    def _update_speed_state(self) -> None:
        for b in self.speed_buttons:
            b.state(["!disabled"] if self.auto_var.get() else ["disabled"])

    def _slide(self, key: str) -> None:
        value = float(round(self.slider_vars[key].get()))
        self._show_slider(key)
        if self.viz.get(key) != value:
            self._set("visualiser", **{key: value})

    def _show_slider(self, key: str) -> None:
        fmt = next(s[4] for s in SLIDERS if s[0] == key)
        self.slider_labels[key].configure(text=fmt.format(round(self.slider_vars[key].get())))

    def _reset_gain(self) -> None:
        self._set("visualiser", sensitivity="medium", **GAIN_DEFAULTS)
        for key, var in self.slider_vars.items():
            var.set(GAIN_DEFAULTS[key])
            self._show_slider(key)
        self.auto_var.set(GAIN_DEFAULTS["auto_gain"])
        self.speed_var.set("medium")
        self._update_speed_state()

    # Macro editor

    def _macro_at(self, x: int, y: int) -> dict | None:
        page = self.page_var.get()
        return next((b for b in self.macros if (b.get("page", 1), b.get("x"), b.get("y")) == (page, x, y)), None)

    def _draw_macro_grid(self) -> None:
        for i, cell in enumerate(self.macro_cells):
            y, x = divmod(i, 8)
            b = self._macro_at(x, y)
            colour = COLOURS.get(b.get("colour", "amber"), (3, 3)) if b else OFF
            fill = led_fill(colour)
            bright = sum(colour) >= 3
            cell.configure(text=(b.get("label", "") if b else "")[:8], bg=fill, activebackground=fill,
                           fg="#000" if bright else "#ddd",
                           relief="sunken" if self.macro_sel == (x, y) else "raised")

    def _select_macro(self, x: int, y: int) -> None:
        self.macro_sel = (x, y)
        b = self._macro_at(x, y) or {}
        self.macro_title.configure(text=f"Page {self.page_var.get()}, pad {x + 1},{y + 1}")
        self.m_label.set(b.get("label", ""))
        self.m_action.set(b.get("action", NO_ACTION))
        self.m_value.set(str(b.get("value", "")))
        self.m_colour.set(b.get("colour", "amber"))
        self._action_changed()
        self._draw_macro_grid()

    def _action_changed(self) -> None:
        action = self.m_action.get()
        self.m_value_box["values"] = list(MEDIA_KEYS) if action == "media" else []
        self.m_hint.configure(text=VALUE_HINTS.get(action, ""))

    def _form_button(self) -> dict | None:
        if self.macro_sel is None or self.m_action.get() in ("", NO_ACTION):
            return None
        x, y = self.macro_sel
        return {"page": self.page_var.get(), "x": x, "y": y, "action": self.m_action.get(),
                "value": self.m_value.get().strip(), "colour": self.m_colour.get() or "amber",
                "label": self.m_label.get().strip()}

    def _store_macros(self) -> None:
        self._set("macro_pad", buttons=copy.deepcopy(self.macros))
        self._draw_macro_grid()

    def _save_macro(self) -> None:
        if self.macro_sel is None:
            return
        self._remove_selected()
        button = self._form_button()
        if button:
            self.macros.append(button)
        self._store_macros()

    def _clear_macro(self) -> None:
        if self.macro_sel is None:
            return
        self._remove_selected()
        self._store_macros()
        self._select_macro(*self.macro_sel)

    def _remove_selected(self) -> None:
        old = self._macro_at(*self.macro_sel)
        if old:
            self.macros.remove(old)

    def _test_macro(self) -> None:
        button = self._form_button()
        if button:
            threading.Thread(target=run_action, args=(button,), daemon=True).start()

    # Preview clicks act as device buttons

    def _press(self, index: int) -> None:
        self._pressed = index
        self.app.device.events.put(led_event(index, True))

    def _release(self) -> None:
        if self._pressed is not None:
            self.app.device.events.put(led_event(self._pressed, False))
            self._pressed = None

    def show(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def hide(self) -> None:
        self.root.withdraw()
        if self.tray and not self._told_about_tray:
            self._told_about_tray = True
            self.tray.notify("Still running in the tray. Right-click the icon to quit.")

    def quit(self) -> None:
        self.root.destroy()

    # Periodic refresh

    def _tick_preview(self) -> None:
        leds = self.app.last_frame.leds
        if leds != self._shown:
            for i, c in enumerate(leds):
                if not self._shown or self._shown[i] != c:
                    self.canvas.itemconfigure(self.items[i], fill=led_fill(c))
            self._shown = list(leds)
        self.root.after(PREVIEW_MS, self._tick_preview)

    def _tick_state(self) -> None:
        while True:
            try:
                msg = self.ui.get_nowait()
            except queue.Empty:
                break
            if msg == "show":
                self.show()
            elif msg == "quit":
                self.quit()
                return
        if not self.worker.is_alive():
            if self.app.crashed:
                messagebox.showerror(TITLE, "Launchpad Lights hit an error and stopped.\n\n"
                                            f"Details are in {app_dir() / 'logs' / 'launchpad-lights.log'}")
            self.quit()
            return
        app = self.app
        bpm = app.audio_bpm()
        self.status.configure(text=f"{app.status}     Audio: {app.audio_device() or '-'}")
        self.bpm_label.configure(text=f"{bpm:.0f} BPM" if bpm else "BPM: listening...")
        if app.slots != self._slots_shown:
            self._rebuild_modes()
        self._sync(self.mode_var, app.mode_name or "")
        self._sync(self.standby_var, app.standby)
        self._sync(self.view_var, int(self.viz.get("sub_mode", 1)))
        self._sync(self.cycle_var, bool(self.viz.get("auto_cycle", False)))
        self._sync(self.speed_var, self.viz.get("sensitivity", "medium"))
        if self._sync(self.auto_var, bool(self.viz.get("auto_gain", True))):
            self._update_speed_state()
        p = POMODORO
        mins, secs = divmod(int(p.left()), 60)
        phase = p.phase.replace("_", " ").capitalize()
        self.pomo_label.configure(text=f"{phase}  {mins:02d}:{secs:02d}{'' if p.running else '  (paused)'}")
        if self.tray:
            self.tray.refresh()
        self.root.after(STATE_MS, self._tick_state)

    @staticmethod
    def _sync(var: tk.Variable, value) -> bool:
        if var.get() != value:
            var.set(value)
            return True
        return False


def run_gui(app, start_hidden: bool = False) -> None:
    ui: queue.Queue = queue.Queue()
    worker = threading.Thread(target=app.run, name="render", daemon=True)
    worker.start()
    root = tk.Tk()
    window = MainWindow(root, app, ui, worker)
    window.tray = Tray(app, ui)
    window.tray.start()
    signal.signal(signal.SIGINT, lambda *_: ui.put("quit"))
    if start_hidden:
        root.withdraw()
    try:
        root.mainloop()
    finally:
        app.stop()
        worker.join(timeout=5)
        window.tray.stop()
