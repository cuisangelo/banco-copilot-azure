from dataclasses import dataclass, field
from typing import Protocol

from bank_contracts.models import ChatAnswer

from copilot_api.workflow.llm import Llm


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


@dataclass
class TurnResult:
    answer: ChatAnswer
    level2_values: list[str] = field(default_factory=list)


class Safety(Protocol):
    async def user_attack(self, text: str) -> bool: ...

    async def document_attacks(self, user_text: str, documents: list[str]) -> list[bool]: ...

    async def ungrounded(self, text: str, sources: list[str]) -> bool: ...


class AuditLog(Protocol):
    async def audit(self, *, actor: str | None, event: str, data: dict) -> None: ...


@dataclass
class Services:
    llm: Llm
    safety: Safety
    store: AuditLog

