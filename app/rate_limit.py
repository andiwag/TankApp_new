"""Rate limiting for auth endpoints (in-memory or Redis-backed)."""

import logging
from collections import defaultdict, deque
from time import monotonic

from app.branding import REDIS_KEY_PREFIX
from app.config import settings

logger = logging.getLogger(__name__)

RATE_LIMIT_MESSAGE = (
    "Zu viele Versuche. Bitte warte eine Minute und versuche es erneut."
)


class InMemoryRateLimiter:
    def __init__(self, *, max_attempts: int, window_seconds: int) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def is_limited(self, key: str) -> bool:
        return len(self._active_attempts(key)) >= self.max_attempts

    def record_attempt(self, key: str) -> None:
        self._active_attempts(key).append(monotonic())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)

    def _active_attempts(self, key: str) -> deque[float]:
        now = monotonic()
        attempts = self._attempts[key]
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()
        return attempts


class RedisRateLimiter:
    def __init__(
        self, *, redis_url: str, max_attempts: int, window_seconds: int
    ) -> None:
        import redis

        self._client = redis.from_url(redis_url, decode_responses=True)
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def _redis_key(self, key: str) -> str:
        return f"{REDIS_KEY_PREFIX}:rate:{key}"

    def is_limited(self, key: str) -> bool:
        redis_key = self._redis_key(key)
        now = monotonic()
        self._client.zremrangebyscore(redis_key, 0, now - self.window_seconds)
        return self._client.zcard(redis_key) >= self.max_attempts

    def record_attempt(self, key: str) -> None:
        redis_key = self._redis_key(key)
        now = monotonic()
        member = f"{now}:{id(self)}"
        pipe = self._client.pipeline()
        pipe.zadd(redis_key, {member: now})
        pipe.zremrangebyscore(redis_key, 0, now - self.window_seconds)
        pipe.expire(redis_key, self.window_seconds + 1)
        pipe.execute()

    def clear(self, key: str) -> None:
        self._client.delete(self._redis_key(key))


def _build_limiter(*, max_attempts: int, window_seconds: int):
    if settings.REDIS_URL:
        try:
            return RedisRateLimiter(
                redis_url=settings.REDIS_URL,
                max_attempts=max_attempts,
                window_seconds=window_seconds,
            )
        except Exception:
            logger.warning(
                "Redis rate limiter unavailable; falling back to in-memory",
                exc_info=True,
            )
    elif settings.is_production:
        logger.warning(
            "REDIS_URL not configured; using in-memory rate limiter in production"
        )
    return InMemoryRateLimiter(
        max_attempts=max_attempts,
        window_seconds=window_seconds,
    )


login_rate_limiter = _build_limiter(max_attempts=5, window_seconds=60)
register_rate_limiter = _build_limiter(max_attempts=10, window_seconds=60)
register_invite_rate_limiter = _build_limiter(max_attempts=15, window_seconds=60)
password_reset_rate_limiter = _build_limiter(max_attempts=5, window_seconds=60)
