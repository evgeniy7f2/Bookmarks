# -*- coding: utf-8 -*-
"""Local Windows install: find/download Python, copy files, venv, autostart.

Everything runs on the machine where the installer was started. No third-party
dependencies — subprocess + registry + PowerShell only.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path

from . import core
from .core import InstallError, wait_health

PYTHON_VERSIONS = core.EMBEDDED_PYTHON_VERSIONS
PYTHON_FULL_URL = "https://www.python.org/ftp/python/{v}/python-{v}-amd64.exe"
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"


def _check_cancel(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise InstallError("err.cancelled")


def _run(cmd: list[str], timeout: int = 1800, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)


# ---------------------------------------------------------------------------
# Python discovery / installation
# ---------------------------------------------------------------------------

def _probe(candidate: str, args: list[str]) -> tuple[str, str] | None:
    """Return (version, executable path) if candidate is a usable Python 3.10+."""
    try:
        proc = _run(
            [candidate] + args + [
                "-c",
                "import sys; print('.'.join(map(str, sys.version_info[:3])))",
            ],
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    ver = proc.stdout.strip()
    m = re.match(r"(\d+)\.(\d+)", ver)
    if not m or int(m.group(1)) < 3 or (int(m.group(1)) == 3 and int(m.group(2)) < 10):
        return None
    try:
        real = str(Path(sys.executable).resolve()) if candidate in ("python", "python3", sys.executable) else candidate
        return ver, real
    except OSError:
        return ver, candidate


def find_python() -> tuple[str, str] | None:
    """Find a usable Python 3.10+ on this machine. Returns (version, path)."""
    candidates = []
    if sys.version_info >= (3, 10):
        candidates.append(sys.executable)
    for launcher in ("py -3", "python", "python3"):
        candidates.append(launcher)
    seen = set()
    for cand in candidates:
        if cand in seen:
            continue
        seen.add(cand)
        if " " in cand:
            exe, _, extra = cand.partition(" ")
            found = _probe(exe, [extra])
            if found:
                return found
            continue
        found = _probe(cand, [])
        if found:
            return found
    # last resort: scan common install locations
    roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs",
        Path("C:/Program Files"),
        Path("C:/Program Files (x86)"),
        Path(os.environ.get("LOCALAPPDATA", "")),
    ]
    for root in roots:
        if not root or not root.exists():
            continue
        for path in sorted(root.glob("Python*")):
            exe = path / "python.exe"
            if exe.exists():
                found = _probe(str(exe), [])
                if found:
                    return found
    return None


def install_python(dest_dir: Path, log, cancel) -> tuple[str, str]:
    """Download and install Python. Returns (version, executable path).

    ``dest_dir`` is the install directory: the embedded fallback unpacks
    straight into <dest_dir>/python so it survives this function.
    """
    _check_cancel(cancel)
    log("step.python.downloading")
    tmp = Path(tempfile.mkdtemp(prefix="bms-py-"))
    try:
        for version in PYTHON_VERSIONS:
            try:
                return _install_python_full(version, tmp, log, cancel)
            except Exception:  # noqa: BLE001 - fall through to the next version
                continue
        return _install_python_embedded(tmp, dest_dir, log, cancel)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _install_python_full(version: str, tmp: Path, log, cancel) -> tuple[str, str]:
    url = PYTHON_FULL_URL.format(v=version)
    installer = tmp / f"python-{version}-amd64.exe"
    core.http_download(url, installer, timeout=900)
    _check_cancel(cancel)
    # silent all-users install first, then per-user (no admin rights needed)
    proc = _run(
        [str(installer), "/quiet", "InstallAllUsers=1", "PrependPath=1",
         "Include_pip=1", "Include_test=0", "Include_tcltk=0", "Include_doc=0"],
        timeout=1200,
    )
    if proc.returncode not in (0, 3010):  # 3010 = "installed for all users"
        proc = _run(
            [str(installer), "/quiet", "InstallAllUsers=0", "PrependPath=1",
             "Include_pip=1", "Include_test=0", "Include_tcltk=0", "Include_doc=0"],
            timeout=1200,
        )
        if proc.returncode != 0:
            raise InstallError("err.no_python")
    found = find_python()
    if found:
        return found
    raise InstallError("err.no_python")


def _install_python_embedded(tmp: Path, dest_dir: Path, log, cancel) -> tuple[str, str]:
    """Fallback: the embeddable package into <dest_dir>/python (no venv, get-pip)."""
    for version in PYTHON_VERSIONS:
        url = PYTHON_EMBED_URL.format(v=version)
        zip_path = tmp / f"python-{version}-embed-amd64.zip"
        try:
            core.http_download(url, zip_path, timeout=900)
        except OSError:
            continue
        _check_cancel(cancel)
        python_dir = dest_dir / "python"
        python_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(python_dir)
        # enable site-packages for pip
        for pth in python_dir.glob("python*._pth"):
            text = pth.read_text(encoding="utf-8", errors="replace")
            pth.write_text(text.replace("#import site", "import site"), encoding="utf-8")
        getpip = tmp / "get-pip.py"
        core.http_download(core.GET_PIP_URL, getpip)
        proc = _run([str(python_dir / "python.exe"), str(getpip)], timeout=900)
        if proc.returncode == 0:
            log("step.python.embedded")
            return version, str(python_dir / "python.exe")
    raise InstallError("err.no_python")


# ---------------------------------------------------------------------------
# file copy
# ---------------------------------------------------------------------------

def copy_project(src: Path, dst: Path, log, cancel) -> int:
    copied = 0
    for path in sorted(src.rglob("*")):
        _check_cancel(cancel)
        rel = path.relative_to(src)
        if any(part in core.COPY_EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.name in core.COPY_EXCLUDE_FILES or path.name.endswith((".log", ".pyc")):
            continue
        target = dst / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        copied += 1
    return copied


# ---------------------------------------------------------------------------
# autostart / shortcut
# ---------------------------------------------------------------------------

def enable_autostart(python: str, install_dir: Path, host: str, port: int) -> None:
    cmd = f'"{python}" "{install_dir / "app.py"}" --host {host} --port {port}'
    _run([
        "reg", "add", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        "/v", "Bookmarks", "/d", cmd, "/f",
    ], timeout=30)


def disable_autostart() -> None:
    _run(["reg", "delete", r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
         "/v", "Bookmarks", "/f"], timeout=30)


def create_start_shortcut(python: str, install_dir: Path, host: str, port: int) -> None:
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$lnk = $ws.CreateShortcut((Join-Path $env:APPDATA 'Microsoft\\Windows\\Start Menu\\Programs\\Bookmarks.lnk')); "
        f"$lnk.TargetPath = {json.dumps(python)}; "
        f"$lnk.Arguments = '--host {host} --port {port}'; "
        f"$lnk.WorkingDirectory = {json.dumps(str(install_dir))}; "
        "$lnk.Description = 'Bookmarks - self-hosted bookmark manager'; "
        "$lnk.Save()"
    )
    _run(["powershell", "-NoProfile", "-Command", ps], timeout=60)


# ---------------------------------------------------------------------------
# main entry
# ---------------------------------------------------------------------------

def install_windows(cfg: dict, log, cancel) -> dict:
    install_dir = Path(cfg["dir"]).expanduser()
    port = cfg["port"]
    host = "0.0.0.0" if cfg.get("network") == "lan" else "127.0.0.1"

    _check_cancel(cancel)
    log("step.python")
    found = find_python()
    if found:
        log("step.python.ok", ver=found[0], path=found[1])
    else:
        log("step.python.missing")
        if not cfg.get("python_auto"):
            raise InstallError("err.no_python")
        found = install_python(install_dir, log, cancel)

    python_exe = found[1]
    _check_cancel(cancel)
    log("step.copy")
    install_dir.mkdir(parents=True, exist_ok=True)
    src = core.INSTALLER_DIR.parent
    if (src / "app.py").exists():
        log("step.copy.local")
    else:
        log("step.copy.download")
        tmp = Path(tempfile.mkdtemp(prefix="bms-src-"))
        try:
            core.http_download(core.BRANCH_ZIP, tmp / "src.zip", timeout=600)
            with zipfile.ZipFile(tmp / "src.zip") as zf:
                zf.extractall(tmp)
            src = next(p for p in tmp.rglob("app.py")).parent
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    copied = copy_project(src, install_dir, log, cancel)
    log("step.copy.ok", n=copied)

    # virtual environment (or direct install for the embedded package)
    _check_cancel(cancel)
    log("step.venv")
    venv_dir = install_dir / ".venv"
    venv_python = venv_dir / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    has_venv = False
    probe = _run([python_exe, "-c", "import venv, ensurepip"], timeout=60)
    if probe.returncode == 0:
        _run([python_exe, "-m", "venv", str(venv_dir)], timeout=300)
        has_venv = venv_python.exists()
    if has_venv:
        _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], timeout=300)
        _run([str(venv_python), "-m", "pip", "install", "-r", str(install_dir / "requirements.txt")],
             timeout=900)
        run_python = str(venv_python)
    else:
        _run([python_exe, "-m", "pip", "install", "-r", str(install_dir / "requirements.txt")],
             timeout=900)
        run_python = python_exe
    log("step.venv.ok")

    data_dir = install_dir / "data"
    data_dir.mkdir(exist_ok=True)
    (install_dir / "install.json").write_text(
        json.dumps(
            {
                "dir": str(install_dir),
                "port": port,
                "host": host,
                "python": run_python,
                "autostart": bool(cfg.get("autostart")),
                "shortcut": bool(cfg.get("shortcut")),
                "installed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log("step.config")

    if cfg.get("autostart"):
        log("step.autostart")
        enable_autostart(run_python, install_dir, host, port)
        log("step.autostart.ok")
    if cfg.get("shortcut"):
        log("step.shortcut")
        create_start_shortcut(run_python, install_dir, host, port)
        log("step.shortcut.ok")

    log("step.start")
    log_file = open(data_dir / "server.log", "ab")
    if os.name == "nt":
        creationflags = 0x00000010 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
        subprocess.Popen(
            [run_python, "app.py", "--host", host, "--port", str(port), "--data", str(data_dir)],
            cwd=str(install_dir),
            stdout=log_file,
            stderr=log_file,
            creationflags=creationflags,
        )
    else:  # non-Windows dev run (tests)
        proc = subprocess.Popen(
            [run_python, "app.py", "--host", host, "--port", str(port), "--data", str(data_dir)],
            cwd=str(install_dir),
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )
        (data_dir / "server.pid").write_text(str(proc.pid))
        log_file.close()

    log("step.health")
    _check_cancel(cancel)
    health = wait_health("127.0.0.1", port, timeout=90, cancel=cancel)
    if not health or not health.get("ok"):
        raise InstallError("err.health", log=str(data_dir / "server.log"))
    log("step.health.ok", ver=health.get("version", "?"), schema=health.get("schema", "?"))

    result = {
        "url": f"http://{'127.0.0.1' if host == '127.0.0.1' else core.local_ip()}:{port}",
        "log": str(data_dir / "server.log"),
        "dir": str(install_dir),
        "version": health.get("version", "?"),
    }
    if cfg.get("open_browser"):
        log("step.open")
        import webbrowser

        webbrowser.open(result["url"])
    return result


def read_install_file(install_dir: Path) -> dict | None:
    try:
        return json.loads((install_dir / "install.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
