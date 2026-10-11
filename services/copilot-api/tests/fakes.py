import json
from collections.abc import Callable
from typing import Any

from agent_framework import ChatResponse, Message
from pydantic import BaseModel


class FakeChatClient:
    """Chat client that answers each structured-output call from a per-schema script.

    A script entry is either a fixed model instance or a callable that receives the prompt text.
    """

    def __init__(self, script: dict[type[BaseModel], BaseModel | Callable[[str], BaseModel]] | None = None) -> None:
        self.script = dict(script or {})
        self.prompts: list[str] = []

    async def get_response(self, messages, *, stream: bool = False, options: Any = None, **kwargs: Any) -> ChatResponse:
        schema = options["response_format"]
        prompt = "\n".join(message.text for message in messages)
        self.prompts.append(prompt)
        entry = self.script[schema]
        value = entry(prompt) if callable(entry) else entry
        return ChatResponse(
            messages=[Message("assistant", [json.dumps(value.model_dump(mode="json"))])],
            response_format=schema,
            usage_details={"input_token_count": 1000, "output_token_count": 200},
        )


class FakeSafety:
    def __init__(self, *, user_attack: bool = False, attacked_snippets: tuple[str, ...] = (), ungrounded: bool = False):
        self._user_attack = user_attack
        self._attacked = attacked_snippets
        self._ungrounded = ungrounded

    async def user_attack(self, text: str) -> bool:
        return self._user_attack

    async def document_attacks(self, user_text: str, documents: list[str]) -> list[bool]:
        return [any(snippet in document for snippet in self._attacked) for document in documents]

    async def ungrounded(self, text: str, sources: list[str]) -> bool:
        return self._ungrounded


class FakeRetriever:
    def __init__(self, chunks):
        self.chunks = chunks
        self.queries: list[str] = []

    async def search(self, query: str, *, top: int):
        self.queries.append(query)
        return self.chunks[:top]
