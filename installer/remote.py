# -*- coding: utf-8 -*-
"""Remote installs over SSH: Linux (systemd) and Docker.

paramiko is the only third-party dependency; if it is missing, it is
installed once into a cache directory via ``pip install --target``.

All user-visible text goes through i18n (keys + kwargs), the same way
the GUI reports progress via the ``log(key, **kw)`` callback.
"""
from __future__ import annotations

import io
import os
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from pathlib import Path

from . import core
from .core import InstallError, local_ip, wait_health

GET_PIP_URL = core.GET_PIP_URL

SYSTEMD_UNIT = """\
[Unit]
Description=Bookmarks - self-hosted bookmark manager
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory={dir}
ExecStart={dir}/.venv/bin/python app.py --host 0.0.0.0 --port {port}
Environment=BOOKMARKS_DATA={dir}/data
Restart=always
RestartSec=3
User={user}

[Install]
WantedBy=multi-user.target
"""


class SshError(InstallError):
    pass


# ---------------------------------------------------------------------------
# paramiko bootstrap
# ---------------------------------------------------------------------------

def _cache_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    else:
        base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "bookmarks-installer" / "pylibs"


def ensure_paramiko(log) -> "module":  # noqa: F821
    try:
        import paramiko  # type: ignore

        return paramiko
    except ImportError:
        pass
    cache = _cache_dir()
    if not (cache / "paramiko").exists():
        log("step.paramiko")
        probe = subprocess.run([sys.executable, "-m", "pip", "--version"],
                               capture_output=True, timeout=60)
        if probe.returncode != 0:
            getpip = Path(tempfile.gettempdir()) / "bms-get-pip.py"
            core.http_download(GET_PIP_URL, getpip)
            subprocess.run([sys.executable, str(getpip)], capture_output=True, timeout=600)
        cache.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--target", str(cache), "paramiko"],
            capture_output=True, text=True, timeout=900,
        )
        if proc.returncode != 0:
            raise SshError("err.paramiko", detail=(proc.stderr or proc.stdout)[-300:])
    if str(cache) not in sys.path:
        sys.path.insert(0, str(cache))
    import paramiko  # type: ignore  # noqa: E402

    return paramiko


# ---------------------------------------------------------------------------
# SSH client
# ---------------------------------------------------------------------------

class SshClient:
    def __init__(self, ip: str, ssh_port: int, user: str, password: str | None):
        self.ip = ip
        self.ssh_port = ssh_port
        self.user = user
        self.password = password
        self.client = None

    def connect(self, log) -> None:
        paramiko = ensure_paramiko(log)
        log("step.connect", ip=self.ip)

        def _ok(_host, _key):
            return True

        try:
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(
                self.ip,
                port=self.ssh_port,
                username=self.user,
                password=self.password or None,
                timeout=20,
                allow_agent=False,
                look_for_keys=True,
                banner_timeout=30,
                auth_timeout=30,
                key_filename=None,
            )
        except paramiko.AuthenticationException:
            raise SshError("err.ssh_auth") from None
        except Exception as exc:  # noqa: BLE001 - surfaced as a friendly error
            raise SshError("err.ssh_failed", detail=_short(exc)) from None
        log("step.connect.ok", user=self.user)

    def run(self, cmd: str, sudo: bool = False, timeout: int = 600,
            stdin_text: str | None = None) -> tuple[int, str, str]:
        if self.client is None:
            raise SshError("err.ssh_failed", detail="not connected")
        full = self._wrap_sudo(cmd) if sudo else cmd
        try:
            _stdin, out, err = self.client.exec_command(
                full, timeout=timeout,
            )
            if stdin_text is not None:
                handle = _stdin if hasattr(_stdin, "write") else _stdin.channel.make_file("wb")
                handle.write(stdin_text.encode("utf-8"))
                if hasattr(handle, "channel"):
                    handle.channel.shutdown_write()
                else:
                    _stdin.channel.shutdown_write()
            data_out, data_err = _read_pair(out, err, timeout)
            rc = out.channel.recv_exit_status()
            return rc, data_out, data_err
        except Exception as exc:  # noqa: BLE001
            raise SshError("err.ssh_failed", detail=_short(exc)) from None

    def run_checked(self, cmd: str, sudo: bool = False, timeout: int = 600,
                    stdin_text: str | None = None) -> str:
        rc, out, err = self.run(cmd, sudo=sudo, timeout=timeout, stdin_text=stdin_text)
        if rc != 0:
            raise SshError("err.remote_cmd", cmd=cmd[:120], detail=(out + "\n" + err)[-400:])
        return out

    def put_file(self, local: Path, remote: str) -> None:
        sftp = self.client.open_sftp()
        try:
            sftp.put(str(local), remote)
        finally:
            sftp.close()

    def _wrap_sudo(self, cmd: str) -> str:
        if self.user == "root":
            return cmd
        if self.password:
            return (
                f"printf '%s' {shlex.quote(self.password)} | "
                f"sudo -S -p '' bash -c {shlex.quote(cmd)}"
            )
        return f"sudo -n bash -c {shlex.quote(cmd)}"

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.close()
            finally:
                self.client = None


def _read(stream, timeout: int) -> str:
    """Read a paramiko ChannelFile (stdout/stderr of ``exec_command``) to EOF.

    ``exec_command(timeout=...)`` already bounds the underlying channel read, so
    a blocking ``read()`` cannot hang past ``timeout`` (it raises instead, and
    the caller wraps that into an :class:`SshError`).
    """
    data = stream.read()
    return data.decode("utf-8", "replace")


def _read_pair(out, err, timeout: int) -> tuple[str, str]:
    """Drain stdout and stderr in parallel to avoid channel-buffer deadlock.

    Reading one stream to EOF before the other can hang when the remote
    process fills the un-read stream's buffer (docker build, apt, pip ...).
    """
    result = {"out": "", "err": ""}
    lock = threading.Lock()

    def _drain(key: str, stream) -> None:
        with lock:
            result[key] = stream.read().decode("utf-8", "replace")

    err_thread = threading.Thread(target=_drain, args=("err", err), daemon=True)
    err_thread.start()
    _drain("out", out)
    err_thread.join(timeout + 5)
    return result["out"], result["err"]


def _short(exc: Exception) -> str:
    return " ".join(str(exc).split())[:200]


def _cancelled(cancel) -> bool:
    return cancel is not None and cancel.is_set()


def _check_cancel(cancel) -> None:
    if _cancelled(cancel):
        raise InstallError("err.cancelled")


# ---------------------------------------------------------------------------
# shared steps
# ---------------------------------------------------------------------------

def default_remote_dir(client: SshClient) -> str:
    if client.user == "root":
        return "/opt/bookmarks"
    home = client.run_checked("printf %s \"$HOME\"").strip()
    return f"{home}/bookmarks"


def prepare_dir(client: SshClient, remote_dir: str, log, cancel) -> None:
    _check_cancel(cancel)
    rc, _out, _err = client.run(f"test -d {shlex.quote(remote_dir)}")
    if rc != 0:
        client.run_checked(f"mkdir -p {shlex.quote(remote_dir)}", sudo=True)
        client.run_checked(f"chown {shlex.quote(client.user)} {shlex.quote(remote_dir)}", sudo=True)


def upload_project(client: SshClient, src: Path, remote_dir: str, log, cancel) -> None:
    """Tar the project locally, stream it over SFTP, extract on the server."""
    _check_cancel(cancel)
    tmp = Path(tempfile.mkdtemp(prefix="bms-upd-"))
    tar_path = tmp / "bookmarks-src.tar"
    try:
        with tarfile.open(tar_path, "w") as tf:
            for path in sorted(src.rglob("*")):
                rel = path.relative_to(src)
                if any(part in core.COPY_EXCLUDE_DIRS for part in rel.parts):
                    continue
                if path.name in core.COPY_EXCLUDE_FILES:
                    continue
                tf.add(path, arcname=str(rel), recursive=False)
        remote_tar = f"/tmp/bookmarks-src-{int(time.time())}.tar"
        client.put_file(tar_path, remote_tar)
        client.run_checked(
            f"tar -xf {shlex.quote(remote_tar)} -C {shlex.quote(remote_dir)} "
            f"&& rm -f {shlex.quote(remote_tar)}",
        )
    finally:
        import shutil

        shutil.rmtree(tmp, ignore_errors=True)


def ensure_python(client: SshClient, log, cancel) -> str:
    _check_cancel(cancel)
    log("step.python.linux")
    rc, out, _err = client.run("python3 --version 2>&1")
    if rc == 0:
        log("step.python.linux.ok", ver=out.strip())
        return out.strip()
    _check_cancel(cancel)
    log("step.python.linux.install")
    rc, _out, err = client.run(
        "command -v apt-get >/dev/null && sudo apt-get update -y && "
        "sudo apt-get install -y python3 python3-venv",
        sudo=True,
        timeout=900,
    ) if client.user != "root" else client.run(
        "command -v apt-get >/dev/null && apt-get update -y && "
        "apt-get install -y python3 python3-venv || "
        "(command -v dnf >/dev/null && dnf install -y python3) || "
        "(command -v yum >/dev/null && yum install -y python3)",
        timeout=900,
    )
    if rc != 0:
        rc, _out, err = client.run("python3 --version 2>&1")
        if rc != 0:
            raise SshError("err.remote_cmd", cmd="install python3", detail=_short(err))
    out2 = client.run_checked("python3 --version")
    log("step.python.linux.ok", ver=out2.strip())
    return out2.strip()


# ---------------------------------------------------------------------------
# Linux install (systemd)
# ---------------------------------------------------------------------------

def install_linux(cfg: dict, log, cancel) -> dict:
    client = SshClient(cfg["ip"], cfg["sshport"], cfg["user"], cfg["password"])
    try:
        client.connect(log)
        remote_dir = cfg.get("path", "").strip() or default_remote_dir(client)
        prepare_dir(client, remote_dir, log, cancel)
        _check_cancel(cancel)
        log("step.copy.remote", dir=remote_dir)
        upload_project(client, core.INSTALLER_DIR.parent, remote_dir, log, cancel)
        log("step.copy.remote.ok")
        ensure_python(client, log, cancel)
        _check_cancel(cancel)
        log("step.venv.remote")
        client.run_checked(
            f"cd {shlex.quote(remote_dir)} && python3 -m venv .venv && "
            f".venv/bin/python -m pip install --upgrade pip && "
            f".venv/bin/pip install -r requirements.txt",
            timeout=1200,
        )
        log("step.venv.remote.ok")
        _check_cancel(cancel)
        log("step.systemd")
        unit = SYSTEMD_UNIT.format(dir=remote_dir, port=cfg["port"], user=client.user)
        client.run_checked("systemctl daemon-reload", sudo=True)
        client.run_checked(
            "tee /etc/systemd/system/bookmarks.service > /dev/null",
            sudo=True,
            stdin_text=unit,
        )
        client.run_checked("systemctl enable bookmarks", sudo=True)
        client.run_checked("systemctl restart bookmarks", sudo=True)
        log("step.systemd.ok")
    finally:
        client.close()

    log("step.health.remote", ip=cfg["ip"], port=cfg["port"])
    _check_cancel(cancel)
    health = wait_health(cfg["ip"], cfg["port"], timeout=120, cancel=cancel)
    if not health or not health.get("ok"):
        raise InstallError("err.health", log=f"journalctl -u bookmarks -f")
    log("step.health.remote.ok", ver=health.get("version", "?"))
    return {
        "url": f"http://{cfg['ip']}:{cfg['port']}",
        "logs": "journalctl -u bookmarks -f",
        "dir": remote_dir,
        "version": health.get("version", "?"),
    }


# ---------------------------------------------------------------------------
# Docker install
# ---------------------------------------------------------------------------

def install_docker(cfg: dict, log, cancel) -> dict:
    client = SshClient(cfg["ip"], cfg["sshport"], cfg["user"], cfg["password"])
    try:
        client.connect(log)
        remote_dir = cfg.get("path", "").strip() or default_remote_dir(client)
        prepare_dir(client, remote_dir, log, cancel)
        _check_cancel(cancel)
        log("step.copy.remote", dir=remote_dir)
        upload_project(client, core.INSTALLER_DIR.parent, remote_dir, log, cancel)
        log("step.copy.remote.ok")
        _check_cancel(cancel)
        log("step.docker.check")
        rc, _out, _err = client.run("docker version --format '{{.Server.Version}}' 2>/dev/null")
        if rc != 0:
            log("step.docker.install")
            client.run_checked(
                "command -v curl >/dev/null || "
                "(command -v apt-get >/dev/null && apt-get update -y && apt-get install -y curl) || "
                "(command -v dnf >/dev/null && dnf install -y curl) || "
                "(command -v yum >/dev/null && yum install -y curl)",
                sudo=True,
                timeout=600,
            )
            client.run_checked("curl -fsSL https://get.docker.com | sh", sudo=True, timeout=1800)
            client.run_checked("systemctl enable --now docker", sudo=True, timeout=300)
            log("step.docker.install.ok")
        _check_cancel(cancel)
        log("step.docker.compose")
        rc, _out, _err = client.run("docker compose version")
        compose_cmd = "docker compose"
        if rc != 0:
            rc, _out, _err = client.run("docker-compose version")
            compose_cmd = "docker-compose"
            if rc != 0:
                client.run_checked(
                    "command -v apt-get >/dev/null && apt-get install -y docker-compose-plugin",
                    sudo=True,
                    timeout=600,
                )
                compose_cmd = "docker compose"
        _check_cancel(cancel)
        if cfg["port"] != core.DEFAULT_PORT:
            client.run_checked(
                f"sed -i 's/8765:8765/{cfg['port']}:8765/' {shlex.quote(remote_dir + '/docker-compose.yml')}"
            )
        log("step.docker.build")
        client.run_checked(
            f"cd {shlex.quote(remote_dir)} && {compose_cmd} up -d --build",
            timeout=1800,
        )
        log("step.docker.up.ok")
    finally:
        client.close()

    log("step.health.remote", ip=cfg["ip"], port=cfg["port"])
    _check_cancel(cancel)
    health = wait_health(cfg["ip"], cfg["port"], timeout=180, cancel=cancel)
    if not health or not health.get("ok"):
        raise InstallError("err.health", log=f"docker logs -f bookmarks")
    log("step.health.remote.ok", ver=health.get("version", "?"))
    return {
        "url": f"http://{cfg['ip']}:{cfg['port']}",
        "logs": "docker logs -f bookmarks",
        "dir": remote_dir,
        "version": health.get("version", "?"),
    }
