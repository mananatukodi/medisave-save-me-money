"""Lightweight in-process rate limiting (Phase 3 closes the Phase 1/2 gap).

Scope: single-process deployments (uvicorn workers each get their own bucket).
For multi-instance production, front this with a gateway/Redis limiter — the
interface below is intentionally small so that swap is trivial.
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.security.deps import client_ip

WINDOW_SECONDS = 60


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int = WINDOW_SECONDS):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - self.window_seconds
            while bucket and bucket[0] < cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many requests. Please slow down.",
                )
            bucket.append(now)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


# Limits chosen conservatively for auth (brute-force damping), AI (cost/abuse),
# and public catalog search (scraping/abuse damping).
auth_limiter = SlidingWindowLimiter(max_requests=10)
ai_limiter = SlidingWindowLimiter(max_requests=20)
search_limiter = SlidingWindowLimiter(max_requests=60)


def _limiting_active() -> bool:
    """Limiter is active unless disabled via config or running the test suite."""
    return settings.rate_limit_enabled and settings.env != "test"


def rate_limit_auth(request: Request) -> None:
    if not _limiting_active():
        return  # deterministic test suite; limiter is unit-tested directly
    auth_limiter.check(f"auth:{client_ip(request) or 'unknown'}")


def rate_limit_ai(request: Request) -> None:
    if not _limiting_active():
        return
    ai_limiter.check(f"ai:{client_ip(request) or 'unknown'}")


def rate_limit_search(request: Request) -> None:
    if not _limiting_active():
        return
    search_limiter.check(f"search:{client_ip(request) or 'unknown'}")
