from bank_contracts.models import AccessRequest


class InMemoryStore:
    """Process-local store with the same interface as CosmosStore, for tests and local runs."""

    def __init__(self) -> None:
        self._usage: dict[str, int] = {}
        self.audit_log: list[dict] = []
        self._access_requests: dict[str, AccessRequest] = {}

    async def audit(self, *, actor: str | None, event: str, data: dict) -> None:
        self.audit_log.append({"actor": actor or "anonymous", "event": event, **data})

    async def add_usage(self, day: str, tokens: int) -> None:
        self._usage[day] = self._usage.get(day, 0) + tokens

    async def get_usage(self, day: str) -> int:
        return self._usage.get(day, 0)

    async def create_access_request(self, request: AccessRequest) -> None:
        self._access_requests[request.id] = request

    async def get_access_request(self, request_id: str) -> AccessRequest | None:
        return self._access_requests.get(request_id)
