from collections.abc import Awaitable, Callable

import httpx

SHIELD_API_VERSION = "2024-09-01"
GROUNDEDNESS_API_VERSION = "2024-09-15-preview"


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
        result = await self._post(
            "shieldPrompt", SHIELD_API_VERSION, {"userPrompt": user_text, "documents": documents}
        )
        return [analysis["attackDetected"] for analysis in result["documentsAnalysis"]]

    async def ungrounded(self, text: str, sources: list[str]) -> bool:
        result = await self._post(
            "detectGroundedness",
            GROUNDEDNESS_API_VERSION,
            {"domain": "Generic", "task": "Summarization", "text": text, "groundingSources": sources},
        )
        return result["ungroundedDetected"]
