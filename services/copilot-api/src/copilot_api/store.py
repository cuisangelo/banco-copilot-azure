import uuid
from datetime import UTC, datetime
from typing import Literal

from agent_framework import CheckpointStorage, InMemoryCheckpointStorage, WorkflowCheckpoint
from agent_framework._workflows._checkpoint_encoding import decode_checkpoint_value, encode_checkpoint_value
from agent_framework.exceptions import WorkflowCheckpointException
from azure.core import MatchConditions
from azure.cosmos.aio import ContainerProxy, DatabaseProxy
from azure.cosmos.exceptions import (
    CosmosAccessConditionFailedError,
    CosmosResourceExistsError,
    CosmosResourceNotFoundError,
)
from bank_contracts.models import (
    AccessRequest,
    AccessRequestStatus,
    ChatAnswer,
    Citation,
    Claim,
    CustomerFields,
    CustomerProfile,
    EscalationDecision,
    EscalationDraft,
    Feedback,
    Product,
)
from pydantic import BaseModel
from pydantic_core import TzInfo

from copilot_api.workflow.composer import ComposerOutput, DraftClaim
from copilot_api.workflow.customer import CustomerPlan
from copilot_api.workflow.escalation import EscalationCase
from copilot_api.workflow.products import ProductFindings
from copilot_api.workflow.rag import Chunk
from copilot_api.workflow.router import RouteDecision
from copilot_api.workflow.turn import HistoryEntry, Turn


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


class FeedbackExists(Exception):
    pass


class InMemoryStore:
    """Process-local store with the same interface as CosmosStore, for tests and local runs."""

    def __init__(self) -> None:
        self._usage: dict[str, int] = {}
        self.audit_log: list[dict] = []
        self._access_requests: dict[str, AccessRequest] = {}
        self._sessions: dict[str, SessionRecord] = {}
        self._checkpoints: dict[str, InMemoryCheckpointStorage] = {}
        self._feedback: dict[str, Feedback] = {}

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

    async def create_feedback(self, feedback: Feedback) -> None:
        if feedback.id in self._feedback:
            raise FeedbackExists(feedback.id)
        self._feedback[feedback.id] = feedback

    async def list_feedback(self, limit: int) -> list[Feedback]:
        return sorted(self._feedback.values(), key=lambda feedback: feedback.created_at, reverse=True)[:limit]


CHECKPOINT_TYPES: frozenset[str] = frozenset(
    f"{cls.__module__}:{cls.__qualname__}"
    for cls in (
        AccessRequest,
        ChatAnswer,
        Citation,
        Claim,
        CustomerFields,
        CustomerProfile,
        EscalationDecision,
        EscalationDraft,
        Product,
        ComposerOutput,
        DraftClaim,
        CustomerPlan,
        EscalationCase,
        ProductFindings,
        Chunk,
        RouteDecision,
        HistoryEntry,
        Turn,
        # Datetimes parsed from JSON (access requests read back from Cosmos) carry pydantic's TzInfo.
        TzInfo,
    )
)


def dump_checkpoint(checkpoint: WorkflowCheckpoint) -> dict:
    return encode_checkpoint_value(checkpoint.to_dict())


def load_checkpoint(value: dict) -> WorkflowCheckpoint:
    """Decode with the restricted unpickler: only the types copilot checkpoints carry can be rebuilt."""
    return WorkflowCheckpoint.from_dict(decode_checkpoint_value(value, allowed_types=CHECKPOINT_TYPES))


class CosmosCheckpointStorage:
    """Workflow checkpoints of one session, partitioned by session_id in the `checkpoints` container."""

    def __init__(self, container: ContainerProxy, session_id: str) -> None:
        self._container = container
        self._session_id = session_id

    async def save(self, checkpoint: WorkflowCheckpoint) -> str:
        await self._container.upsert_item({
            "id": checkpoint.checkpoint_id,
            "session_id": self._session_id,
            "workflow_name": checkpoint.workflow_name,
            "timestamp": checkpoint.timestamp,
            "checkpoint": dump_checkpoint(checkpoint),
        })
        return checkpoint.checkpoint_id

    async def load(self, checkpoint_id: str) -> WorkflowCheckpoint:
        try:
            item = await self._container.read_item(checkpoint_id, partition_key=self._session_id)
        except CosmosResourceNotFoundError as error:
            raise WorkflowCheckpointException(f"checkpoint {checkpoint_id} not found") from error
        return load_checkpoint(item["checkpoint"])

    async def list_checkpoints(self, *, workflow_name: str) -> list[WorkflowCheckpoint]:
        items = self._container.query_items(
            "SELECT * FROM c WHERE c.workflow_name = @name ORDER BY c.timestamp",
            parameters=[{"name": "@name", "value": workflow_name}],
            partition_key=self._session_id,
        )
        return [load_checkpoint(item["checkpoint"]) async for item in items]

    async def delete(self, checkpoint_id: str) -> bool:
        try:
            await self._container.delete_item(checkpoint_id, partition_key=self._session_id)
        except CosmosResourceNotFoundError:
            return False
        return True

    async def get_latest(self, *, workflow_name: str) -> WorkflowCheckpoint | None:
        checkpoints = await self.list_checkpoints(workflow_name=workflow_name)
        return checkpoints[-1] if checkpoints else None

    async def list_checkpoint_ids(self, *, workflow_name: str) -> list[str]:
        return [checkpoint.checkpoint_id for checkpoint in await self.list_checkpoints(workflow_name=workflow_name)]


class CosmosStore:
    """State in the `copilot` database: sessions, checkpoints, access_requests, audit and usage."""

    def __init__(self, database: DatabaseProxy) -> None:
        self._sessions = database.get_container_client("sessions")
        self._checkpoints = database.get_container_client("checkpoints")
        self._access_requests = database.get_container_client("access_requests")
        self._audit = database.get_container_client("audit")
        self._usage = database.get_container_client("usage")

    async def audit(self, *, actor: str | None, event: str, data: dict) -> None:
        await self._audit.create_item({
            "id": str(uuid.uuid4()),
            "actor": actor or "anonymous",
            "event": event,
            "at": datetime.now(UTC).isoformat(),
            **data,
        })

    async def add_usage(self, day: str, tokens: int) -> None:
        increment = [{"op": "incr", "path": "/tokens", "value": tokens}]
        try:
            await self._usage.patch_item(day, partition_key=day, patch_operations=increment)
        except CosmosResourceNotFoundError:
            try:
                await self._usage.create_item({"id": day, "day": day, "tokens": tokens})
            except CosmosResourceExistsError:
                await self._usage.patch_item(day, partition_key=day, patch_operations=increment)

    async def get_usage(self, day: str) -> int:
        try:
            return (await self._usage.read_item(day, partition_key=day))["tokens"]
        except CosmosResourceNotFoundError:
            return 0

    async def create_access_request(self, request: AccessRequest) -> None:
        await self._access_requests.create_item(request.model_dump(mode="json"))

    async def _query_requests(self, where: str, parameters: list[dict]) -> list[dict]:
        items = self._access_requests.query_items(f"SELECT * FROM c{where}", parameters=parameters)
        return [item async for item in items]

    async def get_access_request(self, request_id: str) -> AccessRequest | None:
        items = await self._query_requests(" WHERE c.id = @id", [{"name": "@id", "value": request_id}])
        return AccessRequest.model_validate(items[0]) if items else None

    async def list_access_requests(self, status: AccessRequestStatus | None) -> list[AccessRequest]:
        if status is None:
            items = await self._query_requests("", [])
        else:
            items = await self._query_requests(" WHERE c.status = @status", [{"name": "@status", "value": status}])
        return [AccessRequest.model_validate(item) for item in items]

    async def decide_access_request(self, decided: AccessRequest) -> None:
        """Replace a pending request only if nobody changed it since it was read."""
        current = await self._access_requests.read_item(decided.id, partition_key=decided.customer_id)
        if current["status"] != "pending":
            raise AlreadyDecided(decided.id)
        try:
            await self._access_requests.replace_item(
                decided.id,
                decided.model_dump(mode="json"),
                etag=current["_etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except CosmosAccessConditionFailedError as error:
            raise AlreadyDecided(decided.id) from error

    async def get_session(self, session_id: str) -> SessionRecord | None:
        try:
            return SessionRecord.model_validate(await self._sessions.read_item(session_id, partition_key=session_id))
        except CosmosResourceNotFoundError:
            return None

    async def save_session(self, session: SessionRecord) -> None:
        await self._sessions.upsert_item({"id": session.session_id, **session.model_dump(mode="json")})

    async def find_session_by_escalation(self, escalation_id: str) -> SessionRecord | None:
        items = self._sessions.query_items(
            "SELECT * FROM c WHERE c.pending.kind = 'escalation' AND c.pending.request_id = @id",
            parameters=[{"name": "@id", "value": escalation_id}],
        )
        found = [item async for item in items]
        return SessionRecord.model_validate(found[0]) if found else None

    def checkpoint_storage(self, session_id: str) -> CheckpointStorage:
        return CosmosCheckpointStorage(self._checkpoints, session_id)

    async def create_feedback(self, feedback: Feedback) -> None:
        """The id is deterministic per actor and turn, so Cosmos itself rejects a second rating."""
        try:
            await self._audit.create_item({"event": "feedback", **feedback.model_dump(mode="json")})
        except CosmosResourceExistsError as error:
            raise FeedbackExists(feedback.id) from error

    async def list_feedback(self, limit: int) -> list[Feedback]:
        items = self._audit.query_items(
            "SELECT TOP @limit * FROM c WHERE c.event = 'feedback' ORDER BY c.created_at DESC",
            parameters=[{"name": "@limit", "value": limit}],
        )
        return [Feedback.model_validate(item) async for item in items]
