"""Build GITHUB_Files.zip — the installer payload — from the local files.

Usage:
    python build_zip.py

The canonical file set is defined by the github_upload/ tree (the mirror
that ends up on the GitHub repo root). The script re-copies every mirrored
file from the project root (so the mirror never drifts) and packs the
mirror into GITHUB_Files.zip. Run it after project changes so the payload
the installer downloads always matches the working tree.

New project files must first be added to github_upload/ (and to the
Dockerfile / installer if they belong to the runtime).
"""
import pathlib
import sys
import zipfile

root = pathlib.Path(__file__).resolve().parent
mirror = root / "github_upload"
out = root / "GITHUB_Files.zip"


def main() -> int:
    if not mirror.is_dir():
        print(f"MISSING  {mirror}", file=sys.stderr)
        return 1
    files = sorted(p for p in mirror.rglob("*") if p.is_file())
    if not files:
        print("github_upload/ is empty", file=sys.stderr)
        return 1

    synced = 0
    for mirror_path in files:
        rel = mirror_path.relative_to(mirror)
        src = root / rel
        if not src.exists():
            print(f"MISSING  {rel} (not in the project root)", file=sys.stderr)
            return 1
        data = src.read_bytes()
        if data != mirror_path.read_bytes():
            mirror_path.write_bytes(data)
            synced += 1

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for mirror_path in files:
            zf.write(mirror_path, mirror_path.relative_to(mirror).as_posix())
    size = out.stat().st_size
    print(f"OK  GITHUB_Files.zip: {len(files)} files, {size} bytes "
          f"(re-synced {synced} changed file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
