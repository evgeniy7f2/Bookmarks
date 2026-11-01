# -*- coding: utf-8 -*-
"""Build the update tars from the current project files.

Usage:
    python build_tar.py

Produces (the file set mirrors GITHUB_Files.zip exactly):
    update/update_v1_4_1.tar  — the 1.4.1 payload
    update_v1_4_2.tar         — the test "newer" tar (same files, the
                                 version lives only in the archive name)

Run it after any project change that must ship with the next update.
The archives contain the project files only; data/ and .venv/ are
never part of a tar (update.py also skips them when replacing files).
"""
import io
import os
import pathlib
import sys
import tarfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

root = pathlib.Path(__file__).resolve().parent

FILES = [
    ".dockerignore",
    ".gitignore",
    "DOCKER.md",
    "Dockerfile",
    "README.md",
    "README_GITHUB.md",
    "app.py",
    "backup.sh",
    "build_min.py",
    "build_tar.py",
    "build_zip.py",
    "docker-compose.yml",
    "install.sh",
    "manage.py",
    "requirements.txt",
    "run.bat",
    "run.sh",
    "uninstall.md",
    "update.py",
    "installer_bootstrap.py",
]

INSTALLER = [
    "installer/__init__.py",
    "installer/actions.py",
    "installer/core.py",
    "installer/i18n.py",
    "installer/installer.py",
    "installer/remote.py",
    "installer/win.py",
]

OUT_TARS = [
    root / "update" / "update_v1_4_1.tar",
    root / "update_v1_4_2.tar",
]


def main() -> int:
    bm: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root / "bookmarks"):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            bm.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))

    tests: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root / "tests"):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if fn.endswith(".py"):
                tests.append(os.path.relpath(os.path.join(dirpath, fn), root).replace(os.sep, "/"))

    entries = sorted(FILES + INSTALLER + bm + tests + ["update/.gitkeep"])
    missing = [e for e in entries if not (root / e).is_file()]
    if missing:
        print("MISSING:", *missing, sep="\n  ", file=sys.stderr)
        return 1

    for out in OUT_TARS:
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        with tarfile.open(out, "w") as tf:
            for rel in entries:
                tf.add(root / rel, arcname=rel)
        print(f"OK  {out.relative_to(root)}: {len(entries)} files, {out.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
