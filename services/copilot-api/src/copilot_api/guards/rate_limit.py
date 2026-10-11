import time
from collections import defaultdict, deque
from collections.abc import Callable


class RateLimiter:
    """Sliding one-minute window per client IP, held in memory by each replica."""

    def __init__(self, *, per_minute: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._per_minute = per_minute
        self._clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, ip: str) -> bool:
        now = self._clock()
        hits = self._hits[ip]
        while hits and now - hits[0] >= 60:
            hits.popleft()
        if len(hits) >= self._per_minute:
            return False
        hits.append(now)
        return True
