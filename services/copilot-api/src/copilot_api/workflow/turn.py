from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from bank_contracts.models import (
    AccessRequest,
    ChatAnswer,
    CustomerFields,
    CustomerProfile,
    FieldsDenied,
    Level2Field,
    Product,
)

from copilot_api.workflow.llm import Llm

if TYPE_CHECKING:
    from copilot_api.workflow.customer import CustomerPlan
    from copilot_api.workflow.rag import Chunk
    from copilot_api.workflow.router import RouteDecision


@dataclass
class HistoryEntry:
    """One prior exchange of the session, already stripped of level-2 values."""

    question: str
    answer: str
    customer_id: str | None


@dataclass
class Turn:
    session_id: str
    message: str
    customer_id: str | None
    actor: str | None
    history: list[HistoryEntry]
    route: RouteDecision | None = None
    chunks: list[Chunk] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    customer_plan: CustomerPlan | None = None
    profile: CustomerProfile | None = None
    customer_fields: CustomerFields | None = None
    unauthorized_fields: list[Level2Field] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    tool_calls: int = 0


MAX_TOOL_CALLS = 5


def take_tool_call(turn: Turn) -> bool:
    """Spend one call of the per-turn tool budget; False once it is exhausted."""
    if turn.tool_calls >= MAX_TOOL_CALLS:
        return False
    turn.tool_calls += 1
    return True


@dataclass
class TurnResult:
    answer: ChatAnswer
    level2_values: list[str] = field(default_factory=list)


class Safety(Protocol):
    async def user_attack(self, text: str) -> bool: ...

    async def document_attacks(self, user_text: str, documents: list[str]) -> list[bool]: ...

    async def ungrounded(self, text: str, sources: list[str]) -> bool: ...


class WorkflowStore(Protocol):
    async def audit(self, *, actor: str | None, event: str, data: dict) -> None: ...

    async def create_access_request(self, request: AccessRequest) -> None: ...


class BankTools(Protocol):
    async def get_product(self, product_id: str) -> Product: ...

    async def list_products(self, category: str | None) -> list[Product]: ...

    async def compare_products(self, product_ids: list[str]) -> list[Product]: ...

    async def get_customer_profile(self, customer_id: str) -> CustomerProfile: ...

    async def get_customer_fields(
        self, customer_id: str, fields: list[Level2Field]
    ) -> CustomerFields | FieldsDenied: ...


class Retriever(Protocol):
    async def search(self, query: str, *, top: int) -> list[Chunk]: ...


@dataclass
class Services:
    llm: Llm
    safety: Safety
    store: WorkflowStore
    retriever: Retriever
    bank: BankTools
