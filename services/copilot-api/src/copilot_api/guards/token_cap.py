from datetime import UTC, datetime
from typing import Protocol


class UsageStore(Protocol):
    async def add_usage(self, day: str, tokens: int) -> None: ...

    async def get_usage(self, day: str) -> int: ...


class TokenCapExceeded(Exception):
    pass


def utc_day() -> str:
    return datetime.now(UTC).date().isoformat()


class TokenCap:
    def __init__(self, store: UsageStore, *, daily_cap: int) -> None:
        self._store = store
        self._daily_cap = daily_cap

    async def check(self, day: str) -> None:
        if await self._store.get_usage(day) >= self._daily_cap:
            raise TokenCapExceeded(f"daily token cap of {self._daily_cap} reached")

    async def record(self, day: str, tokens: int) -> None:
        await self._store.add_usage(day, tokens)
