# -*- coding: utf-8 -*-
"""High-level installer actions: manual download and updates.

- manual_download: fetch bookmarks-latest.zip from GitHub to a local folder;
- update_local: run update.py in the local install directory (Windows);
- update_linux: SSH to the server and run its update.py;
- update_docker: SSH, upload fresh files, rebuild the image.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from . import core
from .core import InstallError
from .remote import SshClient, default_remote_dir, upload_project, wait_health
from . import win


# ---------------------------------------------------------------------------
# sources
# ---------------------------------------------------------------------------

def fetch_sources(log, cancel) -> Path:
    """Return a directory containing app.py: the local project when the
    installer runs from a source checkout, otherwise a GitHub download."""
    local = core.INSTALLER_DIR.parent
    if (local / "app.py").exists():
        log("step.copy.local")
        return local
    log("step.copy.download")
    tmp = Path(tempfile.mkdtemp(prefix="bms-src-"))
    core.http_download(core.BRANCH_ZIP, tmp / "src.zip", timeout=600)
    import zipfile

    with zipfile.ZipFile(tmp / "src.zip") as zf:
        zf.extractall(tmp)
    candidates = list(tmp.rglob("app.py"))
    if not candidates:
        raise InstallError("err.download", detail="app.py not found in the archive")
    return candidates[0].parent


def manual_download(dest_dir: Path, log, cancel) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    log("step.copy.download")
    target = dest_dir / "bookmarks-latest.zip"
    if target.exists():
        target.unlink()
    core.http_download(core.BRANCH_ZIP, target, timeout=600)
    return target


# ---------------------------------------------------------------------------
# updates
# ---------------------------------------------------------------------------

def _run_update_streaming(python: str, cwd: Path, log, cancel) -> str:
    """Run update.py --yes in cwd, streaming its output to the log."""
    log("step.update.run")
    cmd = [str(python), "update.py", "--yes"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = []
    assert proc.stdout is not None
    for line in proc.stdout:
        if cancel is not None and cancel.is_set():
            proc.kill()
            raise InstallError("err.cancelled")
        line = line.rstrip()
        if line:
            tail.append(line)
            if len(tail) > 200:
                tail.pop(0)
            log("step.update.line", line=line)
    proc.wait()
    if proc.returncode != 0:
        raise InstallError("err.remote_cmd", cmd="update.py", detail="\n".join(tail[-8:]))
    return "\n".join(tail)


def _local_python(install_dir: Path) -> Path:
    info = win.read_install_file(install_dir)
    if info and info.get("python") and Path(info["python"]).exists():
        return Path(info["python"])
    for cand in (install_dir / ".venv" / "Scripts" / "python.exe",
                 install_dir / ".venv" / "bin" / "python",
                 Path(sys.executable) if os.name != "nt" else None):
        if cand and cand.exists():
            return cand
    raise InstallError("err.update_dir")


def update_local(install_dir: Path, log, cancel) -> dict:
    install_dir = Path(install_dir).expanduser().resolve()
    if not (install_dir / "app.py").exists():
        raise InstallError("err.update_dir")
    log("step.update.check")
    current = core.app_version_from_dir(install_dir)
    latest = _latest_version()
    if latest and (core.parse_version(latest) or (0,)) <= (core.parse_version(current) or (0,)):
        log("step.update.uptodate", ver=current)
        return {"version": current, "url": None, "up_to_date": True}
    _run_update_streaming(_local_python(install_dir), install_dir, log, cancel)
    log("step.update.done")
    new_ver = core.app_version_from_dir(install_dir)
    info = win.read_install_file(install_dir) or {}
    port = int(info.get("port", 8765))
    return {
        "version": new_ver,
        "url": f"http://127.0.0.1:{port}",
        "up_to_date": False,
        "dir": str(install_dir),
    }


def _latest_version() -> str | None:
    try:
        latest = core.http_json(f"{core.GITHUB_API}/releases/latest")
        return (latest.get("tag_name") or "").lstrip("v") or None
    except Exception:  # noqa: BLE001 - not fatal: update.py re-checks
        return None


def update_linux(cfg: dict, log, cancel) -> dict:
    client = SshClient(cfg["ip"], cfg["sshport"], cfg["user"], cfg["password"])
    try:
        client.connect(log)
        remote_dir = cfg.get("path", "").strip() or default_remote_dir(client)
        rc, _out, _err = client.run(f"test -f {shlex.quote(remote_dir + '/app.py')}")
        if rc != 0:
            raise InstallError("err.update_dir")
        log("step.update.check")
        current = _remote_version(client, remote_dir)
        latest = _latest_version()
        if latest and (core.parse_version(latest) or (0,)) <= (core.parse_version(current) or (0,)):
            log("step.update.uptodate", ver=current)
            return {"version": current, "url": f"http://{cfg['ip']}:{cfg['port']}", "up_to_date": True}
        rc, out, _err = client.run(f"test -x {shlex.quote(remote_dir + '/.venv/bin/python')}")
        python = f"{remote_dir}/.venv/bin/python" if rc == 0 else "python3"
        client.run_checked(
            f"cd {shlex.quote(remote_dir)} && {python} update.py --yes",
            timeout=1800,
        )
        log("step.update.done")
    finally:
        client.close()

    log("step.health.remote", ip=cfg["ip"], port=cfg["port"])
    health = wait_health(cfg["ip"], cfg["port"], timeout=180, cancel=cancel)
    if not health or not health.get("ok"):
        raise InstallError("err.health", log=f"journalctl -u bookmarks -f")
    return {
        "version": health.get("version", "?"),
        "url": f"http://{cfg['ip']}:{cfg['port']}",
        "up_to_date": False,
    }


def _remote_version(client: SshClient, remote_dir: str) -> str:
    out = client.run_checked(
        f"python3 -c \"import re; t=open({shlex.quote(remote_dir + '/bookmarks/util.py')}, encoding='utf-8').read(); "
        f"m=re.search(r'APP_VERSION.*?\\'([^\\']+)\\'', t); print(m.group(1) if m else '0.0.0')\""
    ).strip()
    return out or "0.0.0"


def update_docker(cfg: dict, log, cancel) -> dict:
    client = SshClient(cfg["ip"], cfg["sshport"], cfg["user"], cfg["password"])
    sources = fetch_sources(log, cancel)
    try:
        client.connect(log)
        remote_dir = cfg.get("path", "").strip() or default_remote_dir(client)
        rc, _out, _err = client.run(f"test -d {shlex.quote(remote_dir)}")
        if rc != 0:
            raise InstallError("err.update_dir")
        log("step.update.run")
        upload_project(client, sources, remote_dir, log, cancel)
        rc, _out, _err = client.run("docker compose version")
        compose_cmd = "docker compose" if rc == 0 else "docker-compose"
        if cfg["port"] != core.DEFAULT_PORT:
            client.run_checked(
                f"sed -i 's/8765:8765/{cfg['port']}:8765/' {shlex.quote(remote_dir + '/docker-compose.yml')}"
            )
        client.run_checked(
            f"cd {shlex.quote(remote_dir)} && {compose_cmd} up -d --build",
            timeout=1800,
        )
        log("step.update.done")
    finally:
        client.close()

    log("step.health.remote", ip=cfg["ip"], port=cfg["port"])
    health = wait_health(cfg["ip"], cfg["port"], timeout=180, cancel=cancel)
    if not health or not health.get("ok"):
        raise InstallError("err.health", log=f"docker logs -f bookmarks")
    return {
        "version": health.get("version", "?"),
        "url": f"http://{cfg['ip']}:{cfg['port']}",
        "up_to_date": False,
    }
