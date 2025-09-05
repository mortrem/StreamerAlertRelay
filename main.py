# main.py

import os
import sys
import json
import subprocess
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import importlib.util
from threading import Thread
from queue import Queue
import queue
import time

from driver import start_driver, stop_driver, event_queue
from sammi import send_to_sammi

CONFIG_FILE = "config.json"
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))


def ensure_playwright_installed():
    """
    Check for a local Playwright Chromium install in ./playwright_home.
    If missing, prompt the user and show an installation window with a progress bar.
    After install, show a confirmation dialog before restarting.
    """
    home = os.path.join(BASE_DIR, "playwright_home")
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = home

    # If the folder doesn't exist or is empty, install.
    if not os.path.isdir(home) or not os.listdir(home):
        # Prompt user to install
        prompt = tk.Tk()
        prompt.withdraw()
        install = messagebox.askyesno(
            "Playwright Required",
            "You need to install Playwright and Chromium to continue.\n\nInstall now?",
            parent=prompt
        )
        prompt.destroy()
        if not install:
            sys.exit(0)

        # Show install progress window
        win = tk.Tk()
        win.title("Installing Playwright…")
        win.resizable(False, False)
        lbl = tk.Label(
            win,
            text="Installing Playwright & Chromium,\nplease wait...",
            padx=20,
            pady=10
        )
        lbl.pack()
        pb = ttk.Progressbar(win, mode="indeterminate", length=300)
        pb.pack(padx=20, pady=(0, 10))
        pb.start(50)
        win.update()

        try:
            # 1) Install the Python package
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "playwright"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            # 2) Download Chromium binaries
            subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ
            )
        except Exception as e:
            pb.stop()
            win.destroy()
            err = tk.Tk()
            err.withdraw()
            messagebox.showerror(
                "Installation Failed",
                f"Could not install Playwright/Chromium:\n{e}",
                parent=err
            )
            err.destroy()
            sys.exit(1)
        else:
            # Stop progress and confirm before restarting
            pb.stop()
            messagebox.showinfo(
                "Installation Complete",
                "Playwright and Chromium have been installed.\n\nThe application will now restart.",
                parent=win
            )
            win.destroy()
            os.execv(sys.executable, [sys.executable] + sys.argv)


def discover_parsers(directory):
    """
    Auto-load every *_parse.py in `directory` that defines
    EVENTS, get_chat_url, and parse_frame.
    """
    parsers = []
    for fname in os.listdir(directory):
        if not fname.endswith("_parse.py"):
            continue
        module_name = fname[:-3]
        path = os.path.join(directory, fname)
        spec = importlib.util.spec_from_file_location(module_name, path)
        if not spec or not spec.loader:
            continue
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception:
            continue
        if (
            hasattr(mod, "EVENTS")
            and hasattr(mod, "get_chat_url")
            and hasattr(mod, "parse_frame")
            and isinstance(mod.EVENTS, (list, tuple))
        ):
            parsers.append(mod)
    return parsers


def load_config():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(zones):
    cfg = {}
    for i, zone in enumerate(zones):
        parser = zone.get_parser()
        if not parser:
            continue
        raw = zone.input_var.get().strip()
        if hasattr(zone, "_placeholder") and raw == zone._placeholder:
            raw = ""
        cfg[f"zone_{i}"] = {
            "parser": parser.__name__,
            "input": raw,
            "filters": {
                ev: bool(var.get()) for ev, var in zone.filter_vars.items()
            }
        }
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# Discover parser modules at startup
PARSERS = discover_parsers(BASE_DIR)


class ZoneFrame(tk.LabelFrame):
    def __init__(self, master, label, config, *args, **kwargs):
        super().__init__(master, text=label, *args, **kwargs)
        self.parser_var   = tk.StringVar()
        self.input_var    = tk.StringVar()
        self.filter_vars  = {}
        self._placeholder = ""

        # Parser dropdown
        self.parser_dropdown = ttk.Combobox(
            self, textvariable=self.parser_var, state="readonly"
        )
        self.parser_dropdown["values"] = [p.__name__ for p in PARSERS]
        self.parser_dropdown.pack(fill=tk.X, padx=4, pady=4)
        self.parser_dropdown.bind("<<ComboboxSelected>>", self._on_parser_change)

        # Input field
        self.input_entry = tk.Entry(self, textvariable=self.input_var)
        self.input_entry.pack(fill=tk.X, padx=4, pady=4)
        self.input_entry.bind("<FocusIn>", self._on_input_focus_in)
        self.input_entry.bind("<FocusOut>", self._on_input_focus_out)

        # Filters container
        self.filter_frame = tk.Frame(self)
        self.filter_frame.pack(fill=tk.BOTH, expand=True)

        # Load saved state if present
        if config:
            self.parser_var.set(config.get("parser", ""))
            self.input_var.set(config.get("input", ""))
            self.update_filters(config.get("filters", {}))

        # Placeholder & auto‐detect trace
        self._add_placeholder()
        self.input_var.trace_add("write", self._detect_parser)

    def get_parser(self):
        name = self.parser_var.get()
        for p in PARSERS:
            if p.__name__ == name:
                return p
        return None

    def _on_parser_change(self, event):
        self.input_var.set("")
        self._placeholder = ""
        self.input_entry.config(fg="black")
        self.update_filters()
        self._add_placeholder()

    def update_filters(self, saved_filters=None):
        if isinstance(saved_filters, tk.Event):
            saved_filters = None
        for w in self.filter_frame.winfo_children():
            w.destroy()
        self.filter_vars.clear()
        parser = self.get_parser()
        if not parser:
            return
        for ev in parser.EVENTS:
            val = 1 if saved_filters is None or saved_filters.get(ev, True) else 0
            var = tk.IntVar(value=val)
            row = tk.Frame(self.filter_frame)
            row.pack(fill=tk.X, padx=2, pady=1)
            tk.Checkbutton(row, variable=var).pack(side=tk.LEFT)
            lbl = parser.TRIGGERS.get(ev, ev)
            tk.Label(row, text=f"{lbl} ({ev})", anchor="w").pack(side=tk.LEFT)
            self.filter_vars[ev] = var

    def _add_placeholder(self):
        if self.input_var.get().strip():
            return
        parser = self.get_parser()
        if parser and hasattr(parser, "INPUT_TYPE"):
            ptype = parser.INPUT_TYPE
        elif parser:
            ptype = "username"
        else:
            ptype = "parser"
        text = f"Enter {ptype}"
        self.input_entry.delete(0, tk.END)
        self.input_entry.insert(0, text)
        self.input_entry.config(fg="gray")
        self._placeholder = text

    def _on_input_focus_in(self, event):
        if self.input_var.get() == self._placeholder:
            self.input_entry.delete(0, tk.END)
            self.input_entry.config(fg="black")
            self._placeholder = ""

    def _on_input_focus_out(self, event):
        if not self.input_var.get().strip():
            self._add_placeholder()

    def _detect_parser(self, *args):
        val = self.input_var.get().strip()
        if not val or val == self._placeholder:
            return
        if not val.lower().startswith(("http://", "https://")):
            return
        current = self.get_parser()
        if current and getattr(current, "INPUT_TYPE", None) == "url":
            return
        for p in PARSERS:
            if getattr(p, "INPUT_TYPE", None) == "url":
                self.parser_var.set(p.__name__)
                self.update_filters()
                self._add_placeholder()
                break


def launch_ui():
    # 1) Ensure Playwright & Chromium are installed
    ensure_playwright_installed()

    # 2) Load saved configuration
    cfg = load_config()

    # 3) Build and launch UI
    root = tk.Tk()
    root.title("Hook Streamer")
    root.geometry("1200x700")

    # Header with Start button
    header = tk.Frame(root)
    header.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
    start_btn = ttk.Button(header, text="Start", command=lambda: on_start(zones))
    start_btn.pack(side=tk.LEFT)

    # Main layout: zones + console
    content = tk.Frame(root)
    content.pack(fill=tk.BOTH, expand=True)

    zones = []
    zone_frame = tk.Frame(content)
    zone_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    for i in range(4):
        zone_cfg = cfg.get(f"zone_{i}", {})
        zf = ZoneFrame(zone_frame, f"Zone {i+1}", zone_cfg)
        zf.grid(row=i//2, column=i%2, padx=10, pady=10, sticky="nsew")
        zone_frame.grid_rowconfigure(i//2, weight=1)
        zone_frame.grid_columnconfigure(i%2, weight=1)
        zones.append(zf)

    console_frame = tk.Frame(content)
    console_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=10, pady=10)
    tk.Label(console_frame, text="Trigger Console:").pack(anchor="w")
    console_log = scrolledtext.ScrolledText(
        console_frame, wrap=tk.WORD, font=("Courier New", 10)
    )
    console_log.pack(fill=tk.BOTH, expand=True)
    console_log.config(state=tk.DISABLED)

    def log_trigger(msg):
        console_log.config(state=tk.NORMAL)
        console_log.insert(tk.END, msg + "\n")
        console_log.see(tk.END)
        console_log.config(state=tk.DISABLED)

    def on_start(zones):
        stop_driver()
        time.sleep(0.5)
        sources = []
        for zone in zones:
            parser = zone.get_parser()
            val    = zone.input_var.get().strip()
            if parser and val and val != zone._placeholder:
                sources.append({"parser": parser, "username": val})
        if sources:
            start_driver(sources)

    def process_events():
        try:
            parser_name, source_id, event_key, trigger, data = event_queue.get(timeout=0.1)
            for zone in zones:
                parser    = zone.get_parser()
                input_val = zone.input_var.get().strip()
                if (
                    parser
                    and parser.__name__ == parser_name
                    and input_val == source_id
                    and event_key in zone.filter_vars
                    and zone.filter_vars[event_key].get()
                ):
                    send_to_sammi({"trigger": trigger, "customData": data})
                    log_trigger(trigger)
        except queue.Empty:
            pass
        root.after(100, process_events)

    def on_close():
        stop_driver()
        save_config(zones)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    process_events()
    root.mainloop()


if __name__ == "__main__":
    launch_ui()