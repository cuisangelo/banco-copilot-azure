class InMemoryStore:
    """Process-local store with the same interface as CosmosStore, for tests and local runs."""

    def __init__(self) -> None:
        self._usage: dict[str, int] = {}
        self.audit_log: list[dict] = []

    async def audit(self, *, actor: str | None, event: str, data: dict) -> None:
        self.audit_log.append({"actor": actor or "anonymous", "event": event, **data})

    async def add_usage(self, day: str, tokens: int) -> None:
        self._usage[day] = self._usage.get(day, 0) + tokens

    async def get_usage(self, day: str) -> int:
        return self._usage.get(day, 0)
