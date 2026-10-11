from collections.abc import Awaitable, Callable

import httpx

from copilot_api.pricing import cost_usd
from copilot_api.workflow.llm import Usage
from copilot_api.workflow.rag import Chunk, Retrieval

# The GA 2026-04-01 retrieve only takes caller-written intents at minimal effort; letting the service
# plan subqueries from the question (messages + reasoning effort) is still preview-only.
AGENTIC_API_VERSION = "2026-08-01-preview"
KNOWLEDGE_SOURCE = "bank-docs-ks"
KNOWLEDGE_BASE = "bank-docs-kb"
SEARCH_SCOPE = "https://search.azure.com/.default"
# Every Chunk field except the score, which the reference carries outside sourceData.
SOURCE_DATA_FIELDS = ("id", "doc_id", "doc_title", "section", "content")


def knowledge_source_definition(index: str) -> dict:
    return {
        "name": KNOWLEDGE_SOURCE,
        "kind": "searchIndex",
        "searchIndexParameters": {
            "searchIndexName": index,
            "sourceDataFields": [{"name": name} for name in SOURCE_DATA_FIELDS],
            "semanticConfigurationName": "default",
        },
    }


def knowledge_base_definition(openai_endpoint: str, deployment: str) -> dict:
    """The planner calls the chat deployment as the search service's managed identity, never with a key."""
    return {
        "name": KNOWLEDGE_BASE,
        "knowledgeSources": [{"name": KNOWLEDGE_SOURCE}],
        "models": [
            {
                "kind": "azureOpenAI",
                # Deployments are named after their model, as gpt-4.1-mini is.
                "azureOpenAIParameters": {"resourceUri": openai_endpoint, "deploymentId": deployment, "modelName": deployment},
            }
        ],
        "outputMode": "extractiveData",
        "retrievalReasoningEffort": {"kind": "low"},
    }


class AgenticRetriever:
    """Agentic retrieval over the bank-docs knowledge base.

    The service plans subqueries from the question (a comparison becomes one query per product), runs
    each with semantic reranking and returns the merged references. Planning runs on the chat deployment,
    so its tokens are reported for the daily cap.
    """

    def __init__(
        self, endpoint: str, *, http: httpx.AsyncClient, token_provider: Callable[[], Awaitable[str]], model: str
    ) -> None:
        self._endpoint = endpoint
        self._http = http
        self._token_provider = token_provider
        self._model = model

    async def search(self, query: str, *, top: int) -> Retrieval:
        response = await self._http.post(
            f"{self._endpoint}/knowledgebases('{KNOWLEDGE_BASE}')/retrieve",
            params={"api-version": AGENTIC_API_VERSION},
            headers={"Authorization": f"Bearer {await self._token_provider()}"},
            json={
                "messages": [{"role": "user", "content": [{"type": "text", "text": query}]}],
                "retrievalReasoningEffort": {"kind": "low"},
                "outputMode": "extractiveData",
                "includeActivity": True,
                "maxOutputDocuments": top,
                "knowledgeSourceParams": [
                    {
                        "kind": "searchIndex",
                        "knowledgeSourceName": KNOWLEDGE_SOURCE,
                        "includeReferences": True,
                        "includeReferenceSourceData": True,
                    }
                ],
            },
        )
        response.raise_for_status()
        # 206 means a subquery failed: answering from the rest would read as "not documented".
        if response.status_code != httpx.codes.OK:
            raise httpx.HTTPStatusError(
                f"partial agentic retrieval ({response.status_code})", request=response.request, response=response
            )
        body = response.json()
        activity = body["activity"]
        planning = [record for record in activity if record["type"] == "modelQueryPlanning"]
        tokens_in = sum(record["inputTokens"] for record in planning)
        tokens_out = sum(record["outputTokens"] for record in planning)
        references = sorted(
            (ref for ref in body["references"] if ref["type"] == "searchIndex"),
            key=lambda ref: ref["rerankerScore"],
            reverse=True,
        )[:top]
        return Retrieval(
            mode="agentic",
            chunks=[
                Chunk(
                    id=ref["sourceData"]["id"],
                    doc_id=ref["sourceData"]["doc_id"],
                    doc_title=ref["sourceData"]["doc_title"],
                    section=ref["sourceData"]["section"],
                    content=ref["sourceData"]["content"],
                    reranker_score=ref["rerankerScore"],
                )
                for ref in references
            ],
            subqueries=[record["searchIndexArguments"]["search"] for record in activity if record["type"] == "searchIndex"],
            usage=Usage(tokens_in, tokens_out, cost_usd(self._model, tokens_in, tokens_out)),
        )
