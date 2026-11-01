"""Frontend regression tests.

Static guards that keep the admin panel in sync with the backend contract
(field names of /api/admin/summary) and free of the class of bugs that
broke the whole panel silently: an undefined variable inside a render
function (a ReferenceError thrown mid-render is swallowed by the
loadAdmin() catch and shown as a generic "no connection to the server").
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "bookmarks" / "static" / "js" / "app.js"
STYLES_CSS = ROOT / "bookmarks" / "static" / "css" / "styles-base.css"
APP_CSS = ROOT / "bookmarks" / "static" / "css" / "app.css"
I18N_JS = ROOT / "bookmarks" / "static" / "js" / "i18n.js"


def _between(text: str, start_marker: str, end_markers) -> str:
    """Slice of *text* from *start_marker* up to the nearest end marker."""
    start = text.index(start_marker)
    ends = [text.index(marker, start + 1) for marker in end_markers]
    return text[start : min(ends)]


def test_admin_row_declares_language_flag():
    """Regression (v1.3.0): renderAdminRow used `en` without declaring it.
    Rendering the signed-in admin's own row raised a ReferenceError, which
    loadAdmin()'s catch turned into the generic network-error state, so the
    panel looked "broken" although the API requests had succeeded."""
    text = APP_JS.read_text(encoding="utf-8")
    body = _between(text, "function renderAdminRow", ["function renderAdminPanel"])
    assert re.search(r"\ben\b\s*\?", body), "expected the row to use the en flag"
    assert re.search(r"const en\s*=", body), (
        "renderAdminRow must declare `const en = state.settings?...` before "
        "using it (regression: ReferenceError broke the whole admin panel)"
    )


def test_admin_cards_read_only_backend_summary_fields(logged_in):
    """The stat cards may only read fields that /api/admin/summary returns.
    Regression: the card read `s.active_30d` while the API sends
    `users_active_30d`, which rendered the value as "undefined"."""
    response = logged_in.get("/api/admin/summary")
    assert response.status_code == 200
    summary = response.get_json()

    text = APP_JS.read_text(encoding="utf-8")
    body = _between(text, "function renderAdminCards", ["function renderAdminRow"])
    accessed = set(re.findall(r"\bs\.([a-zA-Z0-9_]+)", body))
    assert accessed, "no summary fields found in renderAdminCards"
    missing = sorted(field for field in accessed if field not in summary)
    assert not missing, f"fields missing from /api/admin/summary: {missing}"


def test_favicon_fallback_hidden_after_load():
    """Regression (v1.3.1): the host-letter fallback was always rendered
    under the favicon <img> and showed through transparent icons, so after
    replacing a bookmark's icon with a custom one the old letter stayed
    visible behind it. The load event (capture phase, like "error") must
    mark .card-icon and the CSS must hide the fallback while keeping it
    visible for no-favicons mode and failed icons."""
    text = APP_JS.read_text(encoding="utf-8")
    assert re.search(r'addEventListener\(\s*"load"', text), (
        "app.js must attach a load listener for favicons"
    )
    assert "favicon-loaded" in text, (
        "the load handler must add the favicon-loaded class to .card-icon"
    )

    css = STYLES_CSS.read_text(encoding="utf-8")
    loaded = re.search(
        r"\.card-icon\.favicon-loaded\s+\.card-fallback\s*\{[^}]*display:\s*none",
        css,
    )
    assert loaded, "CSS must hide .card-fallback once the icon has loaded"
    override = re.search(
        r"body\.no-favicons\s+\.card-icon\s+\.card-fallback\s*,\s*"
        r"\.card-icon\.favicon-failed\s+\.card-fallback\s*\{[^}]*display:\s*block",
        css,
    )
    assert override, (
        "CSS must keep the fallback visible when favicons are off or failed"
    )
    assert css.index(loaded.group(0)) < css.index(override.group(0)), (
        "the no-favicons/failed fallback override must come after the "
        "favicon-loaded rule to win the specificity tie"
    )


def test_glow_not_clipped_by_scroll_container():
    """Regression (v1.3.1): the card edge glow is a box-shadow that reaches
    ~14px beyond the card edge, but .list-scroll (overflow-x: hidden) had
    only ~3px of horizontal padding, so the glow was cut off on the sides.
    The scroll container must leave at least 1rem of room on each side."""
    css = STYLES_CSS.read_text(encoding="utf-8")
    block = _between(css, ".list-scroll {", ["\n.list {"])
    match = re.search(r"padding:\s*([^;}]+)", block)
    assert match, "no padding rule found in .list-scroll"
    values = match.group(1).split()
    # CSS shorthand: 1 value = all sides, 2 = top/bottom + left/right,
    # 3 = top + left/right + bottom, 4 = top/right/bottom/left.
    if len(values) == 4:
        sides = [values[3], values[1]]
    elif len(values) in (2, 3):
        sides = [values[1]] * 2
    else:
        sides = [values[0]] * 2
    for side in sides:
        parsed = re.fullmatch(r"([\d.]+)rem", side)
        assert parsed, f"expected rem padding in .list-scroll, got {side!r}"
        assert float(parsed.group(1)) >= 1.0, (
            f".list-scroll must keep at least 1rem of horizontal padding "
            f"for the card edge glow, got {side}"
        )


def test_about_dialog_links_repository():
    """The "About" dialog links the public GitHub repository (added in
    v1.3.1). The URL must live in a named REPO_URL constant, be used in
    openAboutDialog() as a real link that opens in a new tab, and its
    label must be translated (about.github in RU and EN)."""
    text = APP_JS.read_text(encoding="utf-8")
    repo = re.search(r'const REPO_URL = "([^"]+)"', text)
    assert repo, "app.js must define a REPO_URL constant"
    assert repo.group(1) == "https://github.com/evgeniy7f2/Bookmarks", (
        f"unexpected repository URL: {repo.group(1)}"
    )

    # openAboutDialog is the last top-level function in app.js, so slice up
    # to the first line-initial closing brace (the function's own `}`).
    body = _between(text, "function openAboutDialog", ["\n}"])
    assert 'href="${REPO_URL}"' in body, (
        "openAboutDialog must link REPO_URL in the dialog body"
    )
    assert 'target="_blank"' in body and "noopener" in body, (
        "the repository link must open in a new tab without a referrer"
    )

    i18n = I18N_JS.read_text(encoding="utf-8")
    ru = _between(i18n, "ru: {", ["\n  en: {"])
    en = _between(i18n, "en: {", ["\n};"])
    assert '"about.github"' in ru, "RU strings must contain about.github"
    assert '"about.github"' in en, "EN strings must contain about.github"

    css = APP_CSS.read_text(encoding="utf-8")
    assert re.search(r"\.about-repo\s+a\s*\{[^}]*color:\s*var\(--accent\)", css), (
        "app.css must style the .about-repo link with the accent color"
    )


def test_profile_dialog_buttons_moved_up():
    """The Profile dialog used to put both submit buttons at the bottom of
    their forms, which made the dialog taller than the viewport and forced a
    scrollbar. The "Save profile" button now sits on the avatar row
    (.profile-head-actions, submitting profileForm via the `form` attribute)
    and "Change password" sits on the section-title row (.section-head).
    The old .form-actions rows inside both forms must be gone."""
    text = APP_JS.read_text(encoding="utf-8")
    body = _between(text, "function openProfileDialog", ["\n}"])

    assert "profile-head-actions" in body, (
        "openProfileDialog must render .profile-head-actions (save button "
        "moved onto the avatar row)"
    )
    save_block = body[body.index("profile-head-actions"):]
    assert 'form="profileForm"' in save_block.split("</div>")[0], (
        "the save button lives outside the form, so it must keep the "
        "`form=\"profileForm\"` association"
    )
    assert 'profile.changePassword' in body, "change-password label missing"
    section_head = body[body.index("section-head"):]
    assert "profile.password" in section_head.split("</div>")[0], (
        "the password section title must stay inside .section-head"
    )
    assert "profile.changePassword" in section_head.split("</div>")[0], (
        "the change-password button must share the .section-head row"
    )
    for form_id in ("profileForm", "passwordForm"):
        form_block = body[body.index(f'id="{form_id}"') :]
        form_block = form_block[: form_block.index("</form>")]
        assert 'class="form-actions"' not in form_block, (
            f"{form_id} must no longer end with a .form-actions row "
            "(the button was moved to the top)"
        )

    css = APP_CSS.read_text(encoding="utf-8")
    assert re.search(
        r"\.profile-head-actions\s*\{[^}]*margin-left:\s*auto", css
    ), "app.css must right-align .profile-head-actions on the avatar row"
    assert re.search(
        r"\.section-head\s*\{[^}]*display:\s*flex", css
    ), "app.css must lay .section-head out as a flex row"
