from dataclasses import dataclass
from typing import Any, TypeVar

from agent_framework import Message, SupportsChatGetResponse
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Usage:
    tokens_in: int
    tokens_out: int


class Llm:
    """Structured-output calls against the chat deployment, returning the parsed model and its token usage."""

    def __init__(self, client: SupportsChatGetResponse[Any], *, model: str) -> None:
        self._client = client
        self.model = model

    async def structured(self, schema: type[T], *, system: str, user: str) -> tuple[T, Usage]:
        response = await self._client.get_response(
            [Message("system", [system]), Message("user", [user])],
            options={"response_format": schema, "temperature": 0},
        )
        usage = response.usage_details
        return response.value, Usage(usage["input_token_count"], usage["output_token_count"])
