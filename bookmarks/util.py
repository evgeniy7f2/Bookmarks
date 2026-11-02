"""Small dependency-free helpers used across the app.

Only the Python standard library is used here, keeping Flask the single
third-party requirement.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import os
import re
import secrets
import socket
import ssl
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Any

APP_NAME = "Bookmarks"
APP_VERSION = "1.4.1"

# Global quota defaults. An admin can override them per user from the
# admin panel (users.max_* columns); NULL means "use the global value".
MAX_BOOKMARKS_PER_USER = int(os.environ.get("BOOKMARKS_MAX_BOOKMARKS", "5000"))
MAX_TAGS_PER_USER = int(os.environ.get("BOOKMARKS_MAX_TAGS", "100"))
MAX_GROUPS_PER_USER = int(os.environ.get("BOOKMARKS_MAX_GROUPS", "80"))

# Absolute upper bounds for per-user overrides set from the admin panel.
LIMIT_BOUNDS = {
    "bookmarks": (1, 100000),
    "tags": (1, 5000),
    "groups": (1, 500),
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Bookmarks/1.0"
)

# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso(value: datetime | None = None) -> str:
    """ISO-8601 UTC timestamp that JavaScript can parse directly."""
    value = value or utcnow()
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def days_from_now(days: int) -> str:
    return iso(utcnow() + timedelta(days=days))


# How long the Secret group stays open after a successful unlock.
# Activity in the app refreshes the stamp, so an idle browser is re-locked.
SECRET_UNLOCK_TTL = timedelta(minutes=15)


# ---------------------------------------------------------------------------
# Passwords & tokens
# ---------------------------------------------------------------------------

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=32,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, key = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(key)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=base64.b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# URLs & text
# ---------------------------------------------------------------------------

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_TAG_SPLIT_RE = re.compile(r"[,\n]")


def normalize_url(raw: str) -> str:
    """Validate and normalise a user supplied URL (http/https only)."""
    value = (raw or "").strip()
    if not value:
        raise ValueError("URL is required")
    if len(value) > 2000:
        raise ValueError("URL is too long")
    if any(ch in value for ch in "\r\n\t"):
        raise ValueError("URL contains invalid characters")
    if not _SCHEME_RE.match(value):
        value = "https://" + value.lstrip("/")
    parts = urllib.parse.urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise ValueError("Only http and https links are supported")
    if not parts.hostname:
        raise ValueError("URL has no host name")
    if "@" in parts.netloc:
        raise ValueError("URL must not contain credentials")
    try:
        parts.port  # noqa: B018 - validates the port
    except ValueError as exc:
        raise ValueError("URL has an invalid port") from exc
    host = parts.hostname
    if len(host) > 253 or any(ch in host for ch in ' <>\"\\^`{|}'):
        raise ValueError("URL has an invalid host name")
    if not (host == "localhost" or "." in host or ":" in host):
        raise ValueError("URL has an invalid host name")
    path = parts.path or "/"
    return urllib.parse.urlunsplit((scheme, parts.netloc, path, parts.query, parts.fragment))


def host_of(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def guess_title(url: str) -> str:
    host = host_of(url)
    if not host:
        return url
    try:
        path = urllib.parse.unquote(urllib.parse.urlsplit(url).path).strip("/")
    except ValueError:
        path = ""
    if not path:
        return host
    tail = path.split("/")[-1].replace("-", " ").replace("_", " ").strip()
    if tail and len(tail) <= 60:
        return f"{tail} — {host}"
    return host


def clean_text(value: object, max_len: int, *, multiline: bool = False) -> str:
    if value is None:
        return ""
    text = _CONTROL_RE.sub("", str(value))
    if multiline:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
    else:
        text = " ".join(text.split())
    return text[:max_len].strip()


def parse_tags(value: object, limit: int = 24) -> list[str]:
    if isinstance(value, str):
        parts = _TAG_SPLIT_RE.split(value)
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return []
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        name = " ".join(str(part).replace("#", " ").split()).strip()
        if not name:
            continue
        name = name[:32]
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(name)
        if len(result) >= limit:
            break
    return result


def like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def is_valid_username(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_.\-]{3,32}", value or ""))


def is_valid_color(value: str) -> bool:
    return bool(re.fullmatch(r"#[0-9a-fA-F]{6}", value or ""))


# ---------------------------------------------------------------------------
# Remote page metadata & favicons
# ---------------------------------------------------------------------------


class FetchError(Exception):
    pass


def _allow_private_network() -> bool:
    """Private targets are blocked unless the server owner opts in.

    Fetching favicons/metadata from intranet hosts needs
    ``BOOKMARKS_ALLOW_PRIVATE=1`` (or the legacy ``BOOKMARKS_BLOCK_PRIVATE=0``).
    Everything else is rejected before any connection is made.
    """
    if os.environ.get("BOOKMARKS_ALLOW_PRIVATE", "").strip().lower() in {"1", "true", "yes"}:
        return True
    legacy = os.environ.get("BOOKMARKS_BLOCK_PRIVATE", "").strip().lower()
    return legacy in {"0", "false", "no"}


def _is_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _validated_ip(host: str, port: int) -> str:
    """Resolve *host* once and return the address to connect to.

    Every returned address passes the SSRF check, so connecting to the
    first of them cannot land on a private network (DNS-rebinding window
    is closed: the checked IP and the connected IP are the same resolve).
    """
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise FetchError(str(exc)) from exc
    if not infos:
        raise FetchError("host did not resolve")
    if not _allow_private_network():
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if _is_blocked_ip(ip):
                raise FetchError("private network address blocked")
    return infos[0][4][0]


def assert_fetchable(url: str) -> str:
    """SSRF guard: allow only http(s) to public addresses unless opted in.

    Returns the IP address to connect to (the caller must use it instead
    of re-resolving the hostname, which would reopen the DNS-rebinding gap).
    """
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        raise FetchError("only http and https are supported")
    if parts.username or parts.password:
        raise FetchError("credentials in URL are not allowed")
    host = parts.hostname
    if not host:
        raise FetchError("no host")
    try:
        port = parts.port
    except ValueError:
        raise FetchError("bad port in URL") from None
    return _validated_ip(host, port or (443 if parts.scheme == "https" else 80))


def http_get(
    url: str,
    *,
    accept: str = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    max_bytes: int = 512_000,
    timeout: float = 6.0,
) -> tuple[bytes, str, str]:
    """GET *url* with redirects. Every hop is SSRF-checked and pinned to
    the IP the check resolved, so a fast DNS flip cannot swap the target."""
    final_url = url
    for _hop in range(6):
        pinned_ip = assert_fetchable(final_url)
        parts = urllib.parse.urlsplit(final_url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
        path = parts.path or "/"
        if parts.query:
            path = f"{path}?{parts.query}"
        host_header = f"[{host}]" if ":" in host else host
        if port != (443 if parts.scheme == "https" else 80):
            host_header = f"{host_header}:{port}"
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": accept,
            "Accept-Language": "ru,en;q=0.9",
            "Host": host_header,
            "Connection": "close",
        }
        connection = None
        try:
            if parts.scheme == "https":
                # server_hostname keeps SNI and certificate validation on
                # the real host while the socket is opened to the pinned IP.
                connection = http.client.HTTPSConnection(
                    pinned_ip, port, timeout=timeout, server_hostname=host
                )
            else:
                connection = http.client.HTTPConnection(pinned_ip, port, timeout=timeout)
            connection.request("GET", path, headers=headers)
            response = connection.getresponse()
            payload = response.read(max_bytes)
            content_type = (response.getheader("Content-Type") or "").split(";")[0].strip().lower()
            status = response.status
            location = response.getheader("Location")
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError(str(exc) or "fetch failed") from exc
        finally:
            if connection is not None:
                connection.close()
        if status in (301, 302, 303, 307, 308) and location:
            final_url = urllib.parse.urljoin(final_url, location)
            continue
        if status != 200:
            raise FetchError(f"HTTP {status}")
        return payload, content_type, final_url
    raise FetchError("too many redirects")


_ATTR_RE = re.compile(r"""([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""")
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<(meta|link)\b([^>]*)>", re.IGNORECASE)
_CHARSET_RE = re.compile(r"""charset\s*=\s*["']?([\w.-]+)""", re.IGNORECASE)


def _attrs(raw: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        key = match.group(1).lower()
        value = match.group(2) or match.group(3) or match.group(4) or ""
        found[key] = unescape(value).strip()
    return found


def _decode_html(payload: bytes, content_type_header: str) -> str:
    charset = ""
    header_match = _CHARSET_RE.search(content_type_header or "")
    if header_match:
        charset = header_match.group(1)
    if not charset:
        head = payload[:4096].decode("ascii", "ignore")
        meta_match = _CHARSET_RE.search(head)
        if meta_match:
            charset = meta_match.group(1)
    for candidate in (charset, "utf-8"):
        if not candidate:
            continue
        try:
            return payload.decode(candidate, "replace")
        except LookupError:
            continue
    return payload.decode("utf-8", "replace")


def fetch_page_metadata(url: str, timeout: float = 6.0) -> dict[str, str]:
    """Return title/description/site name for a page. Never raises."""
    result: dict[str, str] = {}
    try:
        payload, content_type, final_url = http_get(
            url,
            accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            max_bytes=450_000,
            timeout=timeout,
        )
    except Exception:  # noqa: BLE001 - metadata is best effort
        return result
    if content_type and "html" not in content_type and "xml" not in content_type:
        return result
    html = _decode_html(payload, content_type)
    title = ""
    meta: dict[str, str] = {}
    for match in _TAG_RE.finditer(html):
        tag = match.group(1).lower()
        attrs = _attrs(match.group(2))
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and "content" in attrs:
                meta[key] = attrs["content"]
        elif tag == "link":
            rel = attrs.get("rel", "").lower()
            if "icon" in rel and attrs.get("href"):
                result.setdefault("icon", urllib.parse.urljoin(final_url, attrs["href"]))
    title_match = _TITLE_RE.search(html)
    if title_match:
        title = clean_text(unescape(title_match.group(1)), 300)
    title = meta.get("og:title") or meta.get("twitter:title") or title
    description = (
        meta.get("og:description")
        or meta.get("twitter:description")
        or meta.get("description")
        or ""
    )
    result.update(
        {
            "title": clean_text(title, 300),
            "description": clean_text(description, 600),
            "site_name": clean_text(meta.get("og:site_name"), 120),
            "host": host_of(final_url),
            "final_url": final_url,
        }
    )
    return result


_IMAGE_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"\x00\x00\x01\x00", "image/x-icon"),
    (b"RIFF", "image/webp"),
)


def _image_mime(payload: bytes, header_type: str) -> str:
    if header_type.startswith("image/"):
        if header_type in {
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "image/svg+xml",
            "image/x-icon",
            "image/vnd.microsoft.icon",
        }:
            return "image/x-icon" if "icon" in header_type else header_type
        return header_type
    for magic, mime in _IMAGE_MAGIC:
        if payload.startswith(magic):
            return mime
    if payload.lstrip().startswith(b"<svg") or b"<svg" in payload[:512]:
        return "image/svg+xml"
    return ""


_DATA_URI_MIMES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}


def validate_image_data_uri(value: Any, max_bytes: int = 2 * 1024 * 1024) -> str | None:
    """Return *value* if it is a valid base64 image data-URI, else None."""
    if not isinstance(value, str):
        return None
    header, sep, payload = value.partition(",")
    if not header.startswith("data:image/") or sep != "," or "base64" not in header:
        return None
    mime = header.removeprefix("data:").split(";", 1)[0]
    if mime not in _DATA_URI_MIMES:
        return None
    try:
        raw = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError):
        return None
    if not raw or len(raw) > max_bytes:
        return None
    if _image_mime(raw, mime) == "":
        return None
    return value


def fetch_favicon(url: str, *, timeout: float = 4.0, known_icon: str | None = None) -> tuple[bytes, str] | None:
    """Try to download a favicon for *url*. Returns (bytes, mime) or None."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    base = f"{parts.scheme}://{parts.netloc}"
    candidates: list[str] = []
    if known_icon:
        candidates.append(known_icon)
    try:
        payload, content_type, final_url = http_get(
            url,
            accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
            max_bytes=200_000,
            timeout=timeout,
        )
        if "html" in content_type or not content_type:
            html = _decode_html(payload, content_type)
            for match in _TAG_RE.finditer(html):
                if match.group(1).lower() != "link":
                    continue
                attrs = _attrs(match.group(2))
                rel = attrs.get("rel", "").lower()
                href = attrs.get("href", "")
                if href and ("icon" in rel or rel == "shortcut"):
                    candidates.append(urllib.parse.urljoin(final_url, href))
    except Exception:  # noqa: BLE001
        pass
    candidates.append(base + "/favicon.ico")

    seen: set[str] = set()
    deadline = time.monotonic() + timeout + 2.0
    for candidate in candidates:
        if candidate in seen or time.monotonic() > deadline:
            continue
        seen.add(candidate)
        if urllib.parse.urlsplit(candidate).scheme not in ("http", "https"):
            continue
        try:
            payload, content_type, _final = http_get(
                candidate,
                accept="image/avif,image/webp,image/png,image/svg+xml,image/*,*/*;q=0.5",
                max_bytes=512_000,
                timeout=min(timeout, 3.0),
            )
        except Exception:  # noqa: BLE001
            continue
        mime = _image_mime(payload, content_type)
        if mime and payload and len(payload) <= 512_000:
            return payload, mime
    return None

