from typing import Literal

from agent_framework import CheckpointStorage, InMemoryCheckpointStorage
from bank_contracts.models import AccessRequest, AccessRequestStatus
from pydantic import BaseModel

from copilot_api.workflow.turn import HistoryEntry


class PendingCheckpoint(BaseModel):
    """A workflow paused on request_info; request_id is the access request id or the escalation id."""

    kind: Literal["access", "escalation"]
    request_id: str
    checkpoint_id: str
    question: str
    customer_id: str | None


class SessionRecord(BaseModel):
    session_id: str
    owner: str | None
    history: list[HistoryEntry] = []
    pending: PendingCheckpoint | None = None


class AlreadyDecided(Exception):
    pass


class InMemoryStore:
    """Process-local store with the same interface as CosmosStore, for tests and local runs."""

    def __init__(self) -> None:
        self._usage: dict[str, int] = {}
        self.audit_log: list[dict] = []
        self._access_requests: dict[str, AccessRequest] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._checkpoints: dict[str, InMemoryCheckpointStorage] = {}

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

    async def list_access_requests(self, status: AccessRequestStatus | None) -> list[AccessRequest]:
        return [request for request in self._access_requests.values() if status in (None, request.status)]

    async def decide_access_request(self, decided: AccessRequest) -> None:
        if self._access_requests[decided.id].status != "pending":
            raise AlreadyDecided(decided.id)
        self._access_requests[decided.id] = decided

    async def get_session(self, session_id: str) -> SessionRecord | None:
        session = self._sessions.get(session_id)
        return session.model_copy(deep=True) if session else None

    async def save_session(self, session: SessionRecord) -> None:
        self._sessions[session.session_id] = session.model_copy(deep=True)

    async def find_session_by_escalation(self, escalation_id: str) -> SessionRecord | None:
        for session in self._sessions.values():
            if session.pending and session.pending.kind == "escalation" and session.pending.request_id == escalation_id:
                return session.model_copy(deep=True)
        return None

    def checkpoint_storage(self, session_id: str) -> CheckpointStorage:
        return self._checkpoints.setdefault(session_id, InMemoryCheckpointStorage())
