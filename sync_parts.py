"""Regenerate *.part.js mirror files from app.js.

app.js is the concatenation of the part files plus a few extra blank lines
placed before the section header comments (three blank lines before a header
instead of two, and one blank line before the dialogs header). This script
rebuilds the concatenation, slices it at the known section headers and writes
the part files back.

Usage:
    python sync_parts.py          # regenerate parts from app.js
    python sync_parts.py --check  # only verify, do not write
"""

import pathlib
import sys

JS_DIR = pathlib.Path(__file__).parent / "bookmarks" / "static" / "js"

PARTS = [
    "core.part.js",
    "core2.part.js",
    "core3.part.js",
    "core4.part.js",
    "core5.part.js",
    "core6.part.js",
    "dialogs.part.js",
]

# (header line, blank lines inside the part before the header)
SECTIONS = [
    ("/* ----------------------------- auth screen ----------------------------- */", 2),
    ("/* ----------------------------- icons ----------------------------- */", 2),
    ("/* ----------------------------- navigation ----------------------------- */", 2),
    ("/* ----------------------------- popovers ----------------------------- */", 2),
    ("/* ----------------------------- drag & drop ----------------------------- */", 2),
    ("/* --------------------------------------------------------------------------", 0),
]


def find_index(lines, value, start=0):
    for i in range(start, len(lines)):
        if lines[i] == value:
            return i
    raise ValueError(f"line not found: {value!r}")


def main():
    check_only = "--check" in sys.argv
    app = (JS_DIR / "app.js").read_text(encoding="utf-8").splitlines()

    # Locate the six section headers and drop the extra blank lines.
    header_idx = []
    remove = set()
    for header, _blank_before in SECTIONS:
        idx = find_index(app, header)
        # one extra blank line directly above the header (or before the two
        # blanks that belong to the next part)
        remove.add(idx - 1)
        header_idx.append(idx)

    concat = [line for i, line in enumerate(app) if i not in remove]

    # Re-locate headers in the concatenation and slice.
    pos = []
    for header, _blank_before in SECTIONS:
        pos.append(find_index(concat, header, pos[-1] if pos else 0))

    starts = [0]
    for idx, (_h, blank) in zip(pos, SECTIONS):
        starts.append(idx - blank)
    ends = starts[1:] + [len(concat)]

    regenerated = {}
    for name, (a, b) in zip(PARTS, zip(starts, ends)):
        regenerated[name] = concat[a:b]

    # sanity: core6 ends with init(); dialogs starts with its header
    assert regenerated["core6.part.js"][-1] == "init();", "core6 must end with init();"
    assert regenerated["dialogs.part.js"][0].startswith("/* ----"), "dialogs must start with header"

    ok = True
    for name in PARTS:
        current = (JS_DIR / name).read_text(encoding="utf-8").splitlines()
        if current != regenerated[name]:
            ok = False
            print(f"[diff] {name}: {len(current)} lines vs regenerated {len(regenerated[name])}")
        else:
            print(f"[ok]   {name}: {len(current)} lines identical")

    if ok:
        print("all part files match app.js")
    elif check_only:
        sys.exit(1)
    else:
        for name in PARTS:
            (JS_DIR / name).write_text("\n".join(regenerated[name]) + "\n", encoding="utf-8")
            print(f"[write] {name}")


if __name__ == "__main__":
    main()
