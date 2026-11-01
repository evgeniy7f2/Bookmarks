# -*- coding: utf-8 -*-
"""Bookmarks installer — a tkinter GUI (RU/EN).

Run:  python installer/installer.py

Screens: language -> method -> config -> progress -> done / error.
All logic lives in core/win/remote/actions; this file only draws and wires.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from installer import actions  # noqa: E402
from installer import i18n  # noqa: E402
from installer import remote, win  # noqa: E402
from installer.core import InstallError, validate_ip, validate_port  # noqa: E402

BG = "#f6f7f9"
CARD = "#ffffff"
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
TEXT = "#1f2937"
MUTED = "#6b7280"
ERROR = "#b91c1c"
OK = "#15803d"
BORDER = "#d1d5db"
SELECTED = "#dbeafe"

METHODS = ["windows", "linux", "docker", "manual", "update"]


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.lang = "ru"
        self.screen = "lang"
        self.method = "windows"
        self.update_kind = "win"
        self.cfg: dict = {}
        self.result: dict | None = None
        self.error: str | None = None
        self.cancel = threading.Event()
        self.q: "queue.Queue[str]" = queue.Queue()
        self.worker: threading.Thread | None = None

        root.title(i18n.t("ru", "app.title"))
        root.geometry("760x600")
        root.minsize(680, 540)
        root.configure(bg=BG)

        self._build_topbar()
        self.container = tk.Frame(root, bg=BG)
        self.container.pack(fill="both", expand=True, padx=18, pady=(6, 14))
        self._render()
        root.after(80, self._poll_queue)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def t(self, key: str, **kw) -> str:
        return i18n.t(self.lang, key, **kw)

    def _build_topbar(self) -> None:
        bar = tk.Frame(self.root, bg=CARD, height=54)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Frame(bar, bg=BORDER, height=1).pack(fill="x", side="bottom")
        left = tk.Frame(bar, bg=CARD)
        left.pack(fill="x", expand=True, padx=18, pady=8)
        tk.Label(left, text="🔖", bg=CARD, font=("Segoe UI Emoji", 15)).pack(side="left")
        tk.Label(
            left, text=self.t("app.name"), bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")
        ).pack(side="left", padx=(10, 8), pady=2)
        tk.Label(left, text=self.t("app.subtitle"), bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(
            side="left", pady=4
        )
        self.lang_var = tk.StringVar(value="Русский")
        combo = ttk.Combobox(
            left, textvariable=self.lang_var, state="readonly", width=11,
            values=["Русский", "English"],
        )
        combo.pack(side="right")
        combo.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._set_lang("ru" if self.lang_var.get() == "Русский" else "en"),
        )

    def _set_lang(self, lang: str) -> None:
        self.lang = lang
        self.root.title(self.t("app.title"))
        self._render()

    def _label(self, parent, key, **kw):
        return tk.Label(parent, text=self.t(key), **kw)

    def _button(self, parent, text, command, primary=False, fg=None):
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=ACCENT if primary else CARD,
            fg="white" if primary else (fg or TEXT),
            activebackground=ACCENT_HOVER if primary else SELECTED,
            activeforeground="white" if primary else TEXT,
            relief="flat",
            padx=16,
            pady=7,
            font=("Segoe UI", 10, "bold" if primary else "normal"),
            cursor="hand2",
            highlightthickness=0,
        )
        return btn

    def _render(self) -> None:
        for child in self.container.winfo_children():
            child.destroy()
        builders = {
            "lang": self._screen_lang,
            "method": self._screen_method,
            "config": self._screen_config,
            "progress": self._screen_progress,
            "done": self._screen_done,
            "error": self._screen_error,
        }
        builders[self.screen]()

    # ------------------------------------------------------------------
    # screens
    # ------------------------------------------------------------------

    def _screen_lang(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, pady=30)
        self._label(frame, "lang.title", fg=TEXT, font=("Segoe UI", 18, "bold")).pack(pady=(0, 6))
        self._label(frame, "lang.hint", fg=MUTED, font=("Segoe UI", 10)).pack(pady=(0, 24))
        for lang_key, label in (("ru", "lang.ru"), ("en", "lang.en")):
            card = tk.Frame(frame, bg=CARD, padx=24, pady=18, cursor="hand2",
                            highlightbackground=BORDER, highlightthickness=1)
            card.pack(fill="x", padx=40, pady=8)
            tk.Label(card, text=("🇷🇺 " if lang_key == "ru" else "🇬🇧 ") + self.t(label),
                     bg=CARD, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
            for w in card.winfo_children():
                w.bind("<Button-1>", lambda _e, k=lang_key: self._pick_lang(k))
            card.bind("<Button-1>", lambda _e, k=lang_key: self._pick_lang(k))
            card.bind(
                "<Enter>", lambda _e, c=card: c.configure(highlightbackground=ACCENT)
            )
            card.bind("<Leave>", lambda _e, c=card: c.configure(highlightbackground=BORDER))

    def _pick_lang(self, lang: str) -> None:
        self.lang = lang
        self.lang_var.set("Русский" if lang == "ru" else "English")
        self.root.title(self.t("app.title"))
        self.screen = "method"
        self._render()

    def _screen_method(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, pady=16)
        self._label(frame, "method.title", fg=TEXT, font=("Segoe UI", 16, "bold")).pack(pady=(0, 4))
        self._label(frame, "method.hint", fg=MUTED, font=("Segoe UI", 10)).pack(pady=(0, 16))
        for m in METHODS:
            key = "win" if m == "windows" else m
            card = tk.Frame(
                frame, bg=SELECTED if m == self.method else CARD,
                padx=18, pady=12, cursor="hand2",
                highlightbackground=ACCENT if m == self.method else BORDER,
                highlightthickness=2 if m == self.method else 1,
            )
            card.pack(fill="x", pady=5)
            tk.Label(card, text=self.t(f"method.{key}.title"), bg=card["bg"], fg=TEXT,
                     font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(card, text=self.t(f"method.{key}.desc"), bg=card["bg"], fg=MUTED,
                     font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(2, 0))
            card.bind("<Button-1>", lambda _e, mm=m: self._pick_method(mm))

        foot = tk.Frame(frame, bg=BG)
        foot.pack(fill="x", pady=(20, 0))
        self._button(foot, self.t("btn.next"), self._to_config, primary=True).pack(side="right")

    def _pick_method(self, m: str) -> None:
        self.method = m
        self._render()

    def _to_config(self) -> None:
        self.screen = "config"
        self.error = None
        self._render()

    # ---------------- config ----------------

    def _entry(self, parent, default=""):
        var = tk.StringVar(value=default)
        e = tk.Entry(
            parent, textvariable=var, relief="solid", bd=1, highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT,
            font=("Segoe UI", 10), fg=TEXT,
        )
        return e

    def _field(self, parent, label_key, hint_key, default=""):
        box = tk.Frame(parent, bg=BG)
        box.pack(fill="x", pady=6)
        self._label(box, label_key, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        e = self._entry(box, default)
        e.pack(fill="x", pady=(3, 1))
        if hint_key:
            self._label(box, hint_key, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        return e

    def _screen_config(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, pady=8)
        title_key = {
            "windows": "cfg.win.title", "linux": "cfg.remote.title", "docker": "cfg.remote.title",
            "manual": "manual.title", "update": "update.title",
        }[self.method]
        self._label(frame, title_key, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w")

        scroll = tk.Frame(frame, bg=BG)
        scroll.pack(fill="both", expand=True, pady=(8, 0))
        canvas = tk.Canvas(scroll, bg=BG, highlightthickness=0)
        bar = ttk.Scrollbar(scroll, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=BG)
        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

        if self.method == "windows":
            self._cfg_windows(inner)
        elif self.method in ("linux", "docker"):
            self._cfg_remote(inner)
        elif self.method == "manual":
            self._cfg_manual(inner)
        elif self.method == "update":
            self._cfg_update(inner)

        self.error_lbl = tk.Label(frame, text="", bg=BG, fg=ERROR, font=("Segoe UI", 9),
                                  justify="left", wraplength=680)
        self.error_lbl.pack(fill="x", pady=(4, 0))

        foot = tk.Frame(frame, bg=BG)
        foot.pack(fill="x", pady=(10, 0))
        self._button(foot, self.t("btn.back"), self._to_method).pack(side="left")
        self._button(foot, self.t("btn.start"), self._start, primary=True).pack(side="right")

    def _cfg_windows(self, inner) -> None:
        self.cfg = {
            "dir": str(Path("C:/Bookmarks") if os.name == "nt" else Path.home() / "Bookmarks"),
            "port": "8765",
            "network": "lan",
            "python_auto": True,
            "autostart": True,
            "shortcut": True,
            "open_browser": True,
        }
        self.w_dir = self._field(inner, "cfg.win.dir.label", "cfg.win.dir.hint", self.cfg["dir"])
        self._button(inner, "📁 …", lambda: self._browse(self.w_dir)).pack(anchor="e", pady=(0, 4))
        self.w_port = self._field(inner, "cfg.port.label", "cfg.port.hint", "8765")
        self.w_net = tk.StringVar(value="lan")
        row = tk.Frame(inner, bg=BG)
        row.pack(fill="x", pady=4)
        self._label(row, "cfg.network.label", fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Radiobutton(row, text=self.t("cfg.network.this"), variable=self.w_net, value="this",
                       bg=BG, fg=TEXT, selectcolor=CARD, font=("Segoe UI", 9)).pack(anchor="w")
        tk.Radiobutton(row, text=self.t("cfg.network.lan"), variable=self.w_net, value="lan",
                       bg=BG, fg=TEXT, selectcolor=CARD, font=("Segoe UI", 9)).pack(anchor="w")
        self.w_pauto = tk.BooleanVar(value=True)
        tk.Checkbutton(inner, text=self.t("cfg.win.python.auto"), variable=self.w_pauto,
                       bg=BG, fg=TEXT, selectcolor=CARD, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=2)
        self.w_auto = tk.BooleanVar(value=True)
        tk.Checkbutton(inner, text=self.t("cfg.win.autostart"), variable=self.w_auto,
                       bg=BG, fg=TEXT, selectcolor=CARD, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=2)
        self.w_short = tk.BooleanVar(value=True)
        tk.Checkbutton(inner, text=self.t("cfg.win.shortcut"), variable=self.w_short,
                       bg=BG, fg=TEXT, selectcolor=CARD, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=2)
        self.w_open = tk.BooleanVar(value=True)
        tk.Checkbutton(inner, text=self.t("cfg.win.openbrowser"), variable=self.w_open,
                       bg=BG, fg=TEXT, selectcolor=CARD, font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=2)

    def _cfg_remote(self, inner, note_key: str | None = None) -> None:
        if note_key is None:
            note_key = f"cfg.remote.{'docker' if self.method == 'docker' else 'linux'}.note"
        self.cfg = {"ip": "", "port": "8765", "sshport": "22", "user": "root", "password": "", "path": ""}
        self.w_ip = self._field(inner, "cfg.remote.server", "cfg.remote.server.hint")
        self.w_port = self._field(inner, "cfg.remote.port", "cfg.remote.port.hint", "8765")
        self.w_sshport = self._field(inner, "cfg.remote.sshport", "cfg.remote.sshport.hint", "22")
        self.w_user = self._field(inner, "cfg.remote.user", "cfg.remote.user.hint", "root")
        pass_box = tk.Frame(inner, bg=BG)
        pass_box.pack(fill="x", pady=6)
        self._label(pass_box, "cfg.remote.pass", fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = tk.Frame(pass_box, bg=BG)
        row.pack(fill="x", pady=(3, 1))
        self.w_pass = self._entry(row)
        self.w_pass.pack(side="left", fill="x", expand=True)
        self.w_pass_show = tk.BooleanVar(value=False)
        self.btn_pass_toggle = self._button(pass_box, self.t("cfg.remote.show"), self._toggle_pass)
        self.btn_pass_toggle.pack(anchor="e", pady=(0, 2))
        self._label(pass_box, "cfg.remote.pass.hint", fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w")
        self._label(inner, note_key, fg=MUTED, font=("Segoe UI", 9),
                    justify="left").pack(fill="x", pady=(2, 6))
        self.w_path = self._field(inner, "cfg.remote.path", "cfg.remote.path.hint")

    def _toggle_pass(self) -> None:
        self.w_pass_show.set(not self.w_pass_show.get())
        self.w_pass.configure(show="" if self.w_pass_show.get() else "*")
        self.btn_pass_toggle.configure(
            text=self.t("cfg.remote.hide" if self.w_pass_show.get() else "cfg.remote.show")
        )

    def _cfg_manual(self, inner) -> None:
        default = str(Path.home() / "Downloads") if os.name == "nt" else str(Path.home() / "Downloads")
        self.cfg = {"dest": default}
        self.w_dest = self._field(inner, "manual.dest.label", "manual.dest.hint", default)
        self._button(inner, "📁 …", lambda: self._browse(self.w_dest)).pack(anchor="e", pady=(0, 4))

    def _cfg_update(self, inner) -> None:
        self.update_kind = "win"
        self.w_kind = tk.StringVar(value="win")
        for key, label in (("win", "update.win"), ("linux", "update.linux"), ("docker", "update.docker")):
            box = tk.Frame(inner, bg=CARD, padx=12, pady=8, cursor="hand2",
                           highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="x", pady=3)
            rb = tk.Radiobutton(box, text=self.t(label), variable=self.w_kind, value=key,
                                bg=CARD, fg=TEXT, selectcolor=SELECTED, font=("Segoe UI", 10),
                                anchor="w", command=self._render_update_kind)
            rb.pack(fill="x")
            self._label(box, f"{label}.desc", fg=MUTED, font=("Segoe UI", 9),
                        justify="left").pack(anchor="w")
        self._upd_frame = tk.Frame(inner, bg=BG)
        self._upd_frame.pack(fill="x", pady=(8, 0))
        self._render_update_kind()

    def _render_update_kind(self) -> None:
        self.update_kind = self.w_kind.get()
        for w in self._upd_frame.winfo_children():
            w.destroy()
        if self.update_kind == "win":
            default = str(Path("C:/Bookmarks") if os.name == "nt" else Path.home() / "Bookmarks")
            self.cfg = {"dir": default}
            self.u_dir = self._field(self._upd_frame, "update.dir.label", "update.dir.hint", default)
        else:
            self._cfg_remote(self._upd_frame, note_key=f"cfg.remote.{self.update_kind}.note")

    # ---------------- validation & start ----------------

    def _browse(self, entry_var) -> None:
        path = filedialog.askdirectory(initialdir=entry_var.get() or str(Path.home()))
        if path:
            entry_var.set(path)

    def _collect(self) -> dict:
        cfg: dict = {}
        if self.method == "windows":
            cfg = {
                "dir": self.w_dir.get().strip(),
                "port": validate_port(self.w_port.get()),
                "network": self.w_net.get(),
                "python_auto": self.w_pauto.get(),
                "autostart": self.w_auto.get(),
                "shortcut": self.w_short.get(),
                "open_browser": self.w_open.get(),
            }
        elif self.method in ("linux", "docker"):
            cfg = {
                "ip": validate_ip(self.w_ip.get()),
                "port": validate_port(self.w_port.get()),
                "sshport": validate_port(self.w_sshport.get()),
                "user": self.w_user.get().strip(),
                "password": self.w_pass.get().strip(),
                "path": self.w_path.get().strip(),
            }
        elif self.method == "manual":
            cfg = {"dest": self.w_dest.get().strip()}
        elif self.method == "update":
            if self.update_kind == "win":
                cfg = {"kind": "win", "dir": self.u_dir.get().strip()}
            else:
                cfg = {
                    "kind": self.update_kind,
                    "ip": validate_ip(self.w_ip.get()),
                    "port": validate_port(self.w_port.get()),
                    "sshport": validate_port(self.w_sshport.get()),
                    "user": self.w_user.get().strip(),
                    "password": self.w_pass.get().strip(),
                    "path": self.w_path.get().strip(),
                }
        return cfg

    def _validate(self, cfg: dict) -> None:
        if self.method == "windows":
            if not cfg["dir"]:
                raise InstallError("err.dir")
        elif self.method in ("linux", "docker"):
            if not cfg["user"]:
                raise InstallError("err.user")
            if cfg["user"] != "root" and not cfg["password"]:
                raise InstallError("err.pass.required")
        elif self.method == "manual":
            if not cfg["dest"]:
                raise InstallError("err.dir")
        elif self.method == "update":
            if cfg["kind"] == "win" and not cfg["dir"]:
                raise InstallError("err.dir")

    def _start(self) -> None:
        try:
            cfg = self._collect()
            self._validate(cfg)
        except InstallError as exc:
            self.cfg = {}
            self.error_lbl.configure(text=self.t(exc.key, **exc.kwargs))
            return
        self.cfg = cfg
        self.cancel.clear()
        self.screen = "progress"
        self._render()
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    # ---------------- progress ----------------

    def _screen_progress(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, pady=8)
        self._label(frame, "progress.title", fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self._label(frame, "progress.wait", fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 8))
        box = tk.Frame(frame, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        box.pack(fill="both", expand=True)
        self.log_text = tk.Text(
            box, height=18, wrap="word", relief="flat", bg="#111827", fg="#d1fae5",
            font=("Consolas", 9), padx=10, pady=8, state="disabled",
        )
        bar = ttk.Scrollbar(box, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=bar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        foot = tk.Frame(frame, bg=BG)
        foot.pack(fill="x", pady=(10, 0))
        self.btn_cancel = self._button(foot, self.t("progress.cancel"), self._cancel)
        self.btn_cancel.pack(side="left")

    def _log(self, key: str, **kw) -> None:
        self.q.put(self.t(key, **kw))

    def _poll_queue(self) -> None:
        try:
            while True:
                line = self.q.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        if self.worker is not None and not self.worker.is_alive() and self.q.empty():
            self._finish()
        self.root.after(80, self._poll_queue)

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _cancel(self) -> None:
        self.cancel.set()

    def _worker(self) -> None:
        try:
            if self.method == "windows":
                self.result = win.install_windows(self.cfg, self._log, self.cancel)
            elif self.method == "linux":
                self.result = remote.install_linux(self.cfg, self._log, self.cancel)
            elif self.method == "docker":
                self.result = remote.install_docker(self.cfg, self._log, self.cancel)
            elif self.method == "manual":
                path = actions.manual_download(Path(self.cfg["dest"]), self._log, self.cancel)
                self.result = {"archive": str(path)}
            elif self.method == "update":
                if self.cfg["kind"] == "win":
                    self.result = actions.update_local(Path(self.cfg["dir"]), self._log, self.cancel)
                elif self.cfg["kind"] == "linux":
                    self.result = actions.update_linux(self.cfg, self._log, self.cancel)
                else:
                    self.result = actions.update_docker(self.cfg, self._log, self.cancel)
        except InstallError as exc:
            self.error = self.t(exc.key, **exc.kwargs)
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            self.error = self.t("err.generic", detail=str(exc))

    def _finish(self) -> None:
        self.worker = None
        if self.error:
            self.screen = "error"
        else:
            self.screen = "done"
        self._render()

    # ---------------- done / error ----------------

    def _screen_done(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, pady=16)
        result = self.result or {}
        if self.method == "manual":
            self._label(frame, "done.manual.title", fg=OK, font=("Segoe UI", 16, "bold")).pack(anchor="w")
            tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", pady=8)
            self._label(frame, "manual.done", fg=TEXT, font=("Segoe UI", 10)).pack(anchor="w")
            path_lbl = tk.Label(frame, text=result.get("archive", ""), bg=BG, fg=ACCENT,
                                font=("Consolas", 10), wraplength=680, justify="left")
            path_lbl.pack(anchor="w", pady=(2, 8))
            self._label(frame, "manual.copy_hint", fg=MUTED, font=("Segoe UI", 9),
                        justify="left").pack(anchor="w", pady=(0, 8))
            btns = tk.Frame(frame, bg=BG)
            btns.pack(anchor="w", pady=(4, 10))
            self._button(btns, self.t("btn.save_instructions"), self._save_manual_txt).pack(side="left", padx=(0, 8))
            self._button(btns, self.t("btn.copy"), self._copy_manual_txt).pack(side="left")
            box = tk.Frame(frame, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
            box.pack(fill="both", expand=True)
            txt = tk.Text(box, relief="flat", bg=CARD, fg=TEXT, font=("Consolas", 9),
                          padx=10, pady=8, wrap="word")
            bar = ttk.Scrollbar(box, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=bar.set)
            txt.insert("1.0", self._manual_instructions())
            txt.configure(state="disabled")
            txt.pack(side="left", fill="both", expand=True)
            bar.pack(side="right", fill="y")
            foot = tk.Frame(frame, bg=BG)
            foot.pack(fill="x", pady=(12, 0))
            self._button(foot, self.t("btn.close"), self.root.destroy, primary=True).pack(side="right")
            return

        self._label(frame, "done.title", fg=OK, font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Frame(frame, bg=BORDER, height=1).pack(fill="x", pady=8)
        url = result.get("url")
        if url:
            self._label(frame, "done.url.label", fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
            row = tk.Frame(frame, bg=BG)
            row.pack(anchor="w", pady=(2, 10))
            tk.Label(row, text=url, bg=BG, fg=ACCENT, font=("Consolas", 12, "bold")).pack(side="left")
            self._button(row, self.t("btn.open_browser"), lambda: self._open(url)).pack(side="left", padx=(14, 0))
        hints = []
        if not result.get("up_to_date"):
            hints.append("done.hint.first")
        port = self.cfg.get("port")
        if self.method in ("linux", "docker") and port:
            hints.append(("done.hint.firewall", {"port": port}))
        logs = {
            "linux": "done.hint.logs.linux",
            "docker": "done.hint.logs.docker",
        }.get(self.method)
        if logs:
            hints.append((logs, {}))
        if result.get("log"):
            hints.append(("done.hint.logs.win", {"path": result["log"]}))
        hints.append(("done.hint.update", {}))
        for h in hints:
            key, kw = h if isinstance(h, tuple) else (h, {})
            tk.Label(frame, text=self.t(key, **kw), bg=BG, fg=MUTED,
                     font=("Segoe UI", 9), justify="left", wraplength=680).pack(anchor="w", pady=2)
        foot = tk.Frame(frame, bg=BG)
        foot.pack(fill="x", pady=(14, 0))
        self._button(foot, self.t("btn.close"), self.root.destroy, primary=True).pack(side="right")

    def _manual_instructions(self) -> str:
        parts = [self.t("manual.instructions.all")]
        for key in ("manual.instructions.win", "manual.instructions.linux", "manual.instructions.docker"):
            parts.append(self.t(key))
        return "\n".join(parts)

    def _save_manual_txt(self) -> None:
        default = (self.result or {}).get("archive")
        base = Path(default).with_suffix(".txt") if default else Path.home() / "bookmarks-manual.txt"
        try:
            base.write_text(self._manual_instructions(), encoding="utf-8")
            messagebox.showinfo(self.t("app.title"), str(base))
        except OSError as exc:
            messagebox.showerror(self.t("app.title"), str(exc))

    def _copy_manual_txt(self) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(self._manual_instructions())

    def _screen_error(self) -> None:
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(fill="both", expand=True, pady=16)
        tk.Label(frame, text="⚠️", bg=BG, font=("Segoe UI", 26)).pack(pady=(0, 6))
        self._label(frame, "error.title", fg=ERROR,
                    font=("Segoe UI", 15, "bold")).pack(anchor="w")
        box = tk.Frame(frame, bg=CARD, highlightbackground=ERROR, highlightthickness=1)
        box.pack(fill="both", expand=True, pady=10)
        txt = tk.Text(box, relief="flat", bg=CARD, fg=TEXT, font=("Consolas", 10),
                      padx=12, pady=10, wrap="word")
        txt.insert("1.0", self.error or "")
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True)
        self._label(frame, "error.fix_and_retry", fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(6, 0))
        foot = tk.Frame(frame, bg=BG)
        foot.pack(fill="x", pady=(14, 0))
        self._button(foot, self.t("btn.back"), self._to_method).pack(side="left")
        self._button(foot, self.t("btn.close"), self.root.destroy).pack(side="right")

    # ---------------- misc ----------------

    def _open(self, url: str) -> None:
        import webbrowser

        webbrowser.open(url)

    def _to_method(self) -> None:
        self.screen = "method"
        self._render()

    def _on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            self.cancel.set()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
