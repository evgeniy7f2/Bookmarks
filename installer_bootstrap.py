# -*- coding: utf-8 -*-
"""Bookmarks — installer bootstrapper (Windows, PyInstaller).

A self-contained .exe (bookmarks_install_v140.exe):

1. downloads the latest release files from GitHub (evgeniy7f2/Bookmarks) —
   the ``GITHUB_Files.zip`` release asset, falling back to the main-branch
   zipball, and finally to a payload embedded inside the exe;
2. extracts them;
3. launches the tkinter installer GUI (installer/installer.py) from the
   downloaded payload, so the user always gets the newest installer code.

Flags (mostly for testing/automation):
  --selftest         run build checks, write %TEMP%\\bms_exe_selftest.txt
  --offline DIR      use DIR as payload without downloading
  --download URL     download a specific zip instead of auto-detect
  --embedded         skip the download, use the payload embedded in the exe
  --version          print bootstrapper version and exit
"""
from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import traceback
import tkinter  # noqa: F401  (payload GUI — keep bundled)
import urllib.request
import webbrowser  # noqa: F401  (used by the payload at runtime — keep bundled)
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk  # noqa: F401  (payload GUI submodules)

REPO = "evgeniy7f2/Bookmarks"
API = f"https://api.github.com/repos/{REPO}"
ASSET_NAME = "GITHUB_Files.zip"
BRANCH_ZIP = f"https://github.com/{REPO}/archive/refs/heads/main.zip"
BOOTSTRAP_VERSION = "1.4.0"

SELFTEST_FILE = Path(os.environ.get("TEMP", tempfile.gettempdir())) / "bms_exe_selftest.txt"
APP_DIR = Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir())) / "bookmarks-installer"
PAYLOAD_DIR = APP_DIR / "payload"
ZIP_PATH = APP_DIR / "payload.zip"
CRASH_LOG = APP_DIR / "installer-crash.log"

FROZEN = getattr(sys, "frozen", False)

BG = "#f6f7f9"
CARD = "#ffffff"
ACCENT = "#2563eb"
TEXT = "#1f2937"
MUTED = "#6b7280"
ERROR = "#b91c1c"
BORDER = "#d1d5db"


def _bootstrap_log(msg: str) -> None:
    """Append a line to the bootstrap log (windowed exe has no console)."""
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        with open(APP_DIR / "bootstrap.log", "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    _bootstrap_log("CRASH:\n" + text)
    try:
        CRASH_LOG.write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        import tkinter as tk
        from tkinter import messagebox

        r = tk.Tk()
        r.withdraw()
        messagebox.showerror("Bookmarks Installer", text[-1800:])
        r.destroy()
    except Exception:
        pass


sys.excepthook = _excepthook


# ---------------------------------------------------------------------------
# GitHub download
# ---------------------------------------------------------------------------

def http_json(url: str, timeout: int = 20):
    req = urllib.request.Request(
        url, headers={"User-Agent": f"BookmarksInstaller/{BOOTSTRAP_VERSION}",
                      "Accept": "application/vnd.github+json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def resolve_download_url() -> "tuple[str, str]":
    """Return (url, source label): latest release asset, else main zipball."""
    try:
        info = http_json(f"{API}/releases/latest")
        for asset in info.get("assets") or []:
            if asset.get("name") == ASSET_NAME:
                return asset["browser_download_url"], f"release {info.get('tag_name', '?')}"
    except Exception as exc:
        _bootstrap_log(f"releases/latest failed: {exc!r}")
    return BRANCH_ZIP, "main branch"


def download(url: str, dest: Path, progress) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": f"BookmarksInstaller/{BOOTSTRAP_VERSION}"})
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as out:
        total = 0
        cl = resp.headers.get("Content-Length")
        if cl:
            try:
                total = int(cl)
            except ValueError:
                total = 0
        got = 0
        last = [0.0]
        while True:
            chunk = resp.read(65536)
            if not chunk:
                break
            out.write(chunk)
            got += len(chunk)
            now = time.time()
            if now - last[0] >= 0.15 or got == total:
                last[0] = now
                progress(got, total)
    return dest


def extract_payload(zip_path: Path) -> "Path | None":
    """Extract zip; return the dir containing installer/ (None if not found)."""
    tmp = PAYLOAD_DIR.with_name("payload.new")
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(tmp)
    if (tmp / "installer").is_dir():
        root = tmp
    else:  # GitHub zipballs wrap everything in a top-level folder
        root = None
        for p in tmp.iterdir():
            if p.is_dir() and (p / "installer").is_dir():
                root = p
                break
    if root is None:
        shutil.rmtree(tmp, ignore_errors=True)
        return None
    if PAYLOAD_DIR.exists():
        shutil.rmtree(PAYLOAD_DIR, ignore_errors=True)
    os.replace(str(root), str(PAYLOAD_DIR))
    if root != tmp and tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    return PAYLOAD_DIR


def embedded_payload_dir() -> "Path | None":
    """Payload embedded in the frozen exe (PyInstaller _MEIPASS), if present."""
    if not FROZEN:
        return None
    base = getattr(sys, "_MEIPASS", None)
    if base and (Path(base) / "installer").is_dir():
        return Path(base)
    return None


# ---------------------------------------------------------------------------
# tkinter: download window + error dialog
# ---------------------------------------------------------------------------

def _center(root, w: int, h: int) -> None:
    root.update_idletasks()
    x = (root.winfo_screenwidth() - w) // 2
    y = max((root.winfo_screenheight() - h) // 3, 40)
    root.geometry(f"{w}x{h}+{x}+{y}")


def _label(root, text, **kw):
    import tkinter as tk

    kw.setdefault("bg", BG)
    kw.setdefault("fg", TEXT)
    kw.setdefault("font", ("Segoe UI", 10))
    return tk.Label(root, text=text, **kw)


def error_dialog(text: str, buttons) -> str:
    """Modal dialog. buttons: list of (value, label); returns the chosen value."""
    import tkinter as tk

    root = tk.Tk()
    root.title("Bookmarks Installer")
    root.configure(bg=BG)
    root.resizable(False, False)
    _center(root, 600, 380)
    _label(root, "⚠️", font=("Segoe UI", 24)).pack(pady=(14, 2))
    _label(root, "Ошибка / Error", fg=ERROR, font=("Segoe UI", 13, "bold")).pack()
    box = tk.Frame(root, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
    box.pack(fill="both", expand=True, padx=18, pady=(8, 8))
    txt = tk.Text(box, height=9, wrap="word", font=("Consolas", 9), relief="flat")
    txt.insert("1.0", (text or "unknown error")[:2500])
    txt.configure(state="disabled")
    txt.pack(fill="both", expand=True)
    res = {"v": buttons[-1][0]}
    bar = tk.Frame(root, bg=BG)
    bar.pack(fill="x", padx=18, pady=(0, 14))
    for value, label in reversed(buttons):
        tk.Button(bar, text=label, width=18, command=lambda v=value: (res.__setitem__("v", v), root.destroy())
                  ).pack(side="left", padx=4)
    root.mainloop()
    return res["v"]


def download_payload(url_override: "str | None") -> "tuple[Path | None, str | None]":
    """Show the download window; return (payload_dir, error)."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(f"Bookmarks Installer v{BOOTSTRAP_VERSION}")
    root.configure(bg=BG)
    root.resizable(False, False)
    _center(root, 500, 240)

    closed = {"v": False}

    def _on_close() -> None:
        closed["v"] = True
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)

    _label(root, "🔖", font=("Segoe UI Emoji", 16)).pack(pady=(14, 0))
    _label(root, "Загрузка с GitHub  •  Downloading from GitHub",
           font=("Segoe UI", 12, "bold")).pack(pady=(2, 8))
    status = _label(root, "Подготовка… / Preparing…", fg=MUTED, font=("Segoe UI", 9),
                    wraplength=450, justify="center")
    status.pack(pady=(4, 6))
    bar = ttk.Progressbar(root, length=420, mode="determinate", maximum=100)
    bar.pack(pady=(0, 8))
    _label(root, "Источник: GitHub  •  Source: github.com", fg=MUTED, font=("Segoe UI", 8)
           ).pack(pady=(0, 12))

    state = {"phase": "start", "error": None, "result": None, "label": "…"}
    bar_max = [0]
    bar_value = [0]

    def set_status(text: str) -> None:
        status.configure(text=text)

    def progress(got: int, total: int) -> None:
        def apply(g=got, t=total):
            if t:
                bar_max[0] = t
                bar_value[0] = g
                set_status(f"{state['label']}\n{g // 1024} / {t // 1024} KB")
            else:
                bar_value[0] = g // 1024
                set_status(f"{state['label']}\n{g // 1024} KB")

        root.after(0, apply)

    def worker() -> None:
        try:
            if url_override:
                url, label = url_override, "custom URL"
            else:
                url, label = resolve_download_url()
            state["label"] = label
            set_status(f"{label}\n{url}")
            _bootstrap_log(f"downloading {label}: {url}")
            if ZIP_PATH.exists():
                ZIP_PATH.unlink()
            download(url, ZIP_PATH, progress)
            set_status(f"{state['label']}\nРаспаковка… / Extracting…")
            root.after(0, lambda: bar.configure(mode="indeterminate", value=0))
            bar.start(12)
            extracted = extract_payload(ZIP_PATH)
            state["result"] = extracted
            state["phase"] = "done" if extracted else "no_installer"
        except Exception:
            state["error"] = traceback.format_exc()
            state["phase"] = "error"

    def poll() -> None:
        if state["phase"] in ("done", "no_installer", "error"):
            try:
                bar.stop()
            except tk.TclError:
                pass
            root.destroy()
            return
        m, v = bar_max[0], bar_value[0]
        if m:
            try:
                bar.configure(mode="determinate", maximum=max(m, 1), value=min(v, m))
            except tk.TclError:
                pass
        try:
            root.after(100, poll)
        except tk.TclError:
            pass

    th = threading.Thread(target=worker, daemon=True)
    th.start()
    root.after(100, poll)
    root.mainloop()
    th.join(timeout=15)

    if state["phase"] not in ("done", "no_installer", "error"):
        if closed["v"]:
            return None, ("Download cancelled (window closed)\nСкачивание отменено (окно закрыто)")
        return None, state["error"] or "unknown download error"
    if state["phase"] == "done":
        return state["result"], None
    if state["phase"] == "no_installer":
        return None, ("The downloaded archive does not contain installer/ "
                      "(GitHub main may be outdated).\nСкачанный архив не содержит installer/ "
                      "(ветка main на GitHub может быть устаревшей).")
    return None, state["error"] or "unknown download error"


# ---------------------------------------------------------------------------
# payload launch
# ---------------------------------------------------------------------------

def _probe_python(path: str) -> bool:
    try:
        out = subprocess.run([path, "-c", "import sys; print(sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=15)
    except Exception:
        return False
    m = re.search(r"\((\d+),\s*(\d+)\)", out.stdout or "")
    return bool(m) and (int(m.group(1)), int(m.group(2))) >= (3, 10)


def find_real_python() -> "str | None":
    """Find a real (non-frozen) Python 3.10+ on this machine, if any."""
    try:
        out = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.lower().endswith(".exe"):
                    cand = line.split()[-1]
                    if _probe_python(cand):
                        return cand
    except Exception:
        pass
    for name in ("python", "python3"):
        p = shutil.which(name)
        if p and _probe_python(p):
            return p
    return None


def fix_executable() -> None:
    """In a frozen exe, sys.executable is the exe itself. The payload uses it
    to run pip / create venvs, so point it at a real Python when one exists."""
    if not FROZEN:
        return
    real = find_real_python()
    _bootstrap_log(f"sys.executable fix: {real!r}")
    sys.executable = real if real else ""


def run_payload(payload_dir: Path) -> int:
    payload_dir = Path(payload_dir)
    _bootstrap_log(f"launching installer from {payload_dir}")
    sys.path.insert(0, str(payload_dir))
    for name in list(sys.modules):
        if name == "installer" or name.startswith("installer."):
            del sys.modules[name]
    gui = importlib.import_module("installer.installer")
    return int(gui.main() or 0)


# ---------------------------------------------------------------------------
# selftest / main
# ---------------------------------------------------------------------------

def selftest() -> int:
    lines = [f"python={sys.version.split()[0]}", f"frozen={FROZEN}",
             f"version={BOOTSTRAP_VERSION}"]
    ok = True

    def check(name: str, fn) -> None:
        nonlocal ok
        try:
            fn()
            lines.append(f"OK   {name}")
        except Exception as exc:  # noqa: BLE001
            ok = False
            lines.append(f"FAIL {name}: {exc!r}")

    def c_tk() -> None:
        import tkinter as tk
        from tkinter import ttk

        r = tk.Tk()
        r.withdraw()
        ttk.Style()
        r.destroy()

    def c_paramiko() -> None:
        import paramiko  # noqa: F401

        assert paramiko.__version__

    def c_embedded() -> None:
        assert embedded_payload_dir() is not None, "embedded payload missing"

    check("tkinter", c_tk)
    if FROZEN:
        check("paramiko", c_paramiko)
        check("embedded-payload", c_embedded)
    text = "\n".join(lines) + "\nSMOKE-" + ("OK" if ok else "FAIL") + "\n"
    try:
        SELFTEST_FILE.write_text(text, encoding="utf-8")
    except OSError:
        pass
    print(text, end="")
    return 0 if ok else 1


def _flag_value(args: list[str], flag: str) -> "str | None":
    if flag in args:
        i = args.index(flag)
        if i + 1 < len(args):
            return args[i + 1]
    return None


def main() -> int:
    args = list(sys.argv[1:])
    if "--version" in args:
        print(f"bookmarks_install {BOOTSTRAP_VERSION}")
        return 0
    if "--selftest" in args:
        return selftest()
    fix_executable()

    offline = _flag_value(args, "--offline")
    url = _flag_value(args, "--download")

    if offline:
        d = Path(offline).resolve()
        if not (d / "installer").is_dir():
            msg = f"--offline: no installer/ in {d}\n--offline: в каталоге нет installer/"
            _bootstrap_log(msg)
            error_dialog(msg, [("exit", "Выход / Exit")])
            return 1
        return run_payload(d)

    if "--embedded" in args:
        emb = embedded_payload_dir()
        if emb:
            return run_payload(emb)
        msg = "No embedded payload (not a frozen build?)\nНет встроенной копии (не .exe?)"
        error_dialog(msg, [("exit", "Выход / Exit")])
        return 1

    while True:
        try:
            payload, err = download_payload(url)
        except Exception:
            payload, err = None, traceback.format_exc()
        if payload is not None:
            return run_payload(payload)
        buttons = [("retry", "Повторить / Retry"), ("exit", "Выход / Exit")]
        if embedded_payload_dir():
            buttons.insert(1, ("embedded", "Встроенная версия / Built-in"))
        choice = error_dialog(err or "unknown", buttons)
        if choice == "embedded":
            emb = embedded_payload_dir()
            if emb:
                return run_payload(emb)
        elif choice == "exit":
            return 1
        # choice == "retry" → loop again


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    raise SystemExit(main())
