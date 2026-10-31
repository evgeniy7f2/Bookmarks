"""Build minified copies of the frontend scripts into bookmarks/static/js/.

Usage:
    python build_min.py

The generated *.min.js files are served in place of the sources from
templates/index.html. Run this script after editing the sources so the
bundle and the fragments never drift apart.

Note: the esbuild 0.12.x binary accepted by this project does not support
--outfile/--outdir, so the minified output is read from stdout.
"""
import pathlib
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parent
static_js = root / "bookmarks" / "static" / "js"

FILES = [
    "theme.js",
    "i18n-early.js",
    "i18n.js",
    "app.js",
]


def minify(source: pathlib.Path, out: pathlib.Path) -> bool:
    result = subprocess.run(
        [
            sys.executable, "-m", "esbuild",
            "--minify",
            "--charset=utf8",
            str(source),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0 or not result.stdout:
        print(f"  esbuild error: {(result.stderr or '').strip()}")
        return False
    out.write_text(result.stdout, encoding="utf-8")
    return True


def main() -> int:
    for name in FILES:
        source = static_js / name
        out = static_js / (name.replace(".js", ".min.js"))
        if not source.exists():
            print(f"MISSING  {source}", file=sys.stderr)
            return 1
        ok = minify(source, out)
        if not ok:
            print(f"FAIL  {source.name} -> {out.name}")
            return 1
        # Keep the minified module graph consistent: app.min.js must import
        # the minified i18n module, not the source one.
        if name == "app.js":
            code = out.read_text(encoding="utf-8")
            out.write_text(code.replace('./i18n.js', './i18n.min.js'), encoding="utf-8")
        size = out.stat().st_size
        print(f"OK  {source.name} -> {out.name} ({size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
