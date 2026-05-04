"""Small in-memory rate limiter for low-volume auth endpoints."""

from collections import defaultdict, deque
from time import monotonic

RATE_LIMIT_MESSAGE = "Too many attempts. Please wait a minute and try again."


class RateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def is_limited(self, key: str) -> bool:
        attempts = self._active_attempts(key)
        return len(attempts) >= self.max_attempts

    def record_attempt(self, key: str) -> None:
        attempts = self._active_attempts(key)
        attempts.append(monotonic())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)

    def _active_attempts(self, key: str) -> deque[float]:
        now = monotonic()
        attempts = self._attempts[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        return attempts


login_rate_limiter = RateLimiter(max_attempts=5, window_seconds=60)
register_rate_limiter = RateLimiter(max_attempts=10, window_seconds=60)
password_reset_rate_limiter = RateLimiter(max_attempts=5, window_seconds=60)
