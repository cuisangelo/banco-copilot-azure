from collections.abc import Awaitable, Callable

import httpx

SHIELD_API_VERSION = "2024-09-01"
GROUNDEDNESS_API_VERSION = "2024-09-15-preview"
# shieldPrompt rejects with 400 more than 5 documents or more than 10,000 characters of documents.
SHIELD_MAX_DOCUMENTS = 5
SHIELD_MAX_DOCUMENT_CHARS = 10_000


def _shield_batches(documents: list[str]) -> list[list[str]]:
    batches: list[list[str]] = [[]]
    for document in documents:
        if len(document) > SHIELD_MAX_DOCUMENT_CHARS:
            raise ValueError(f"document of {len(document)} chars exceeds the Prompt Shields limit")
        batch = batches[-1]
        if len(batch) == SHIELD_MAX_DOCUMENTS or sum(map(len, batch)) + len(document) > SHIELD_MAX_DOCUMENT_CHARS:
            batches.append(batch := [])
        batch.append(document)
    return [batch for batch in batches if batch]


class ContentSafety:
    """Prompt Shields and groundedness detection over the Content Safety REST API.

    Both operations are REST-only; the azure-ai-contentsafety SDK does not expose them.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        http: httpx.AsyncClient,
        token_provider: Callable[[], Awaitable[str]],
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._http = http
        self._token_provider = token_provider

    async def _post(self, operation: str, api_version: str, body: dict) -> dict:
        response = await self._http.post(
            f"{self._endpoint}/contentsafety/text:{operation}",
            params={"api-version": api_version},
            headers={"Authorization": f"Bearer {await self._token_provider()}"},
            json=body,
        )
        response.raise_for_status()
        return response.json()

    async def user_attack(self, text: str) -> bool:
        result = await self._post("shieldPrompt", SHIELD_API_VERSION, {"userPrompt": text, "documents": []})
        return result["userPromptAnalysis"]["attackDetected"]

    async def document_attacks(self, user_text: str, documents: list[str]) -> list[bool]:
        attacks: list[bool] = []
        for batch in _shield_batches(documents):
            result = await self._post(
                "shieldPrompt", SHIELD_API_VERSION, {"userPrompt": user_text, "documents": batch}
            )
            attacks += [analysis["attackDetected"] for analysis in result["documentsAnalysis"]]
        return attacks

    async def ungrounded_percentage(self, text: str, sources: list[str], *, query: str) -> float:
        """Share of the text (0–1) that the sources do not support; 0 when it is fully grounded."""
        # QnA, not Summarization: an answer draws conclusions ("cumple según la ficha") that
        # Summarization flags as ungrounded even when every premise is in the sources.
        result = await self._post(
            "detectGroundedness",
            GROUNDEDNESS_API_VERSION,
            {"domain": "Generic", "task": "QnA", "qna": {"query": query}, "text": text, "groundingSources": sources},
        )
        return float(result["ungroundedPercentage"]) if result["ungroundedDetected"] else 0.0
