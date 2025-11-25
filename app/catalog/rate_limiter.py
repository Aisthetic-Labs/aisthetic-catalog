import asyncio
import time


class SimpleRateLimiter:
    def __init__(self, rate_per_minute: float, burst: int = 1) -> None:
        self.capacity = float(burst)
        self.tokens = float(burst)
        self.rate_per_sec = float(rate_per_minute) / 60.0
        self.last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
            self.last = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            # compute wait for one token
            wait = (1.0 - self.tokens) / max(self.rate_per_sec, 1e-9)
        await asyncio.sleep(wait)
        # recursive ensure token consumed
        await self.acquire()
