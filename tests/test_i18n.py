"""i18n parity: RU and EN must offer the exact same key set, and every
error code the API can return must have a human-readable translation."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
I18N = ROOT / "bookmarks" / "static" / "js" / "i18n.js"


def _block_keys(text: str, lang: str) -> set[str]:
    """Extract the key set of the *lang* object from i18n.js."""
    marker = f'{lang}: {{'
    start = text.index(marker) + len(marker)
    depth = 1
    for index in range(start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                block = text[start:index]
                break
    else:
        raise AssertionError(f"unbalanced braces in {lang} block")
    return set(re.findall(r'"([a-zA-Z0-9_.]+)"\s*:', block))


def test_ru_en_parity():
    text = I18N.read_text(encoding="utf-8")
    ru = _block_keys(text, "ru")
    en = _block_keys(text, "en")
    assert ru, "RU block is empty"
    assert en, "EN block is empty"
    assert not (ru - en), f"missing in EN: {sorted(ru - en)}"
    assert not (en - ru), f"missing in RU: {sorted(en - ru)}"


def test_api_error_codes_are_translated():
    """Every error code emitted by the backend must be translated."""
    codes: set[str] = set()
    for path in (ROOT / "bookmarks").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        codes.update(re.findall(r'_error\(\s*"([a-z0-9_]+)"', text))
        codes.update(re.findall(r'"error":\s*"([a-z0-9_]+)"', text))
    assert codes, "no error codes found in the backend"

    text = I18N.read_text(encoding="utf-8")
    translated = set(re.findall(r'"err\.([a-z0-9_]+)"\s*:', text))
    missing = sorted(code for code in codes if code not in translated)
    assert not missing, f"error codes without a translation: {missing}"
