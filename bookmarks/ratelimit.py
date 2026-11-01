"""In-memory rate limiting shared by login and the secret-group unlock.

A single bucket per key keeps at most ``LIMIT`` timestamps inside the
``WINDOW`` seconds. Stale keys are pruned on access and whenever the table
grows past ``MAX_KEYS``, so the dict cannot grow without bound.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

LIMIT = 8
WINDOW = 300.0
MAX_KEYS = 10_000

_attempts: dict[str, deque[float]] = defaultdict(deque)


def _prune(bucket: deque[float], now: float) -> None:
    while bucket and now - bucket[0] > WINDOW:
        bucket.popleft()


def _sweep(now: float) -> None:
    stale = [key for key, bucket in _attempts.items() if not bucket or now - bucket[-1] > WINDOW]
    for key in stale:
        _attempts.pop(key, None)
    if len(_attempts) > MAX_KEYS:
        _attempts.clear()


def is_limited(key: str) -> bool:
    """Whether *key* already used up its attempts inside the window."""
    now = time.time()
    bucket = _attempts.get(key)
    if bucket is None:
        return False
    _prune(bucket, now)
    if not bucket:
        _attempts.pop(key, None)
        return False
    return len(bucket) >= LIMIT


def remember(key: str) -> None:
    """Record one failed attempt for *key*."""
    now = time.time()
    if len(_attempts) >= MAX_KEYS:
        _sweep(now)
    bucket = _attempts[key]
    _prune(bucket, now)
    bucket.append(now)


def reset(key: str) -> None:
    """Forget the attempts of *key* (successful call)."""
    _attempts.pop(key, None)
