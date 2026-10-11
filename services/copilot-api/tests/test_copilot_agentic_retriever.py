import json

import httpx
import pytest

from copilot_api.workflow.agentic import (
    AGENTIC_API_VERSION,
    KNOWLEDGE_BASE,
    KNOWLEDGE_SOURCE,
    AgenticRetriever,
    knowledge_base_definition,
    knowledge_source_definition,
)
from copilot_api.workflow.rag import Chunk

ENDPOINT = "https://search.example"


def reference(doc_key: str, score: float, activity: int) -> dict:
    doc_id, section = doc_key.rsplit("-", 1)
    return {
        "type": "searchIndex",
        "id": f"ref-{doc_key}",
        "activitySource": activity,
        "rerankerScore": score,
        "docKey": doc_key,
        "sourceData": {
            "id": doc_key,
            "doc_id": doc_id,
            "doc_title": f"Ficha {doc_id}",
            "section": section,
            "content": f"Contenido de {doc_key}",
        },
    }


# Shape of the 200 sample in the Knowledge Retrieval - Retrieve reference for 2026-08-01-preview.
PLANNED_RESPONSE = {
    "response": [{"content": [{"type": "text", "text": "[{...}]"}]}],
    "activity": [
        {
            "type": "modelQueryPlanning",
            "id": 0,
            "elapsedMs": 640,
            "inputTokens": 1200,
            "outputTokens": 80,
            "model": {"modelName": "gpt-4.1-mini", "deploymentId": "gpt-4.1-mini"},
        },
        {
            "type": "searchIndex",
            "id": 1,
            "knowledgeSourceName": KNOWLEDGE_SOURCE,
            "count": 1,
            "elapsedMs": 210,
            "searchIndexArguments": {"search": "requisitos tarjeta Oro", "semanticConfigurationName": "default"},
        },
        {
            "type": "searchIndex",
            "id": 2,
            "knowledgeSourceName": KNOWLEDGE_SOURCE,
            "count": 2,
            "elapsedMs": 190,
            "searchIndexArguments": {"search": "requisitos tarjeta Platinum", "semanticConfigurationName": "default"},
        },
        {"type": "agenticReasoning", "id": 3, "reasoningTokens": 310, "retrievalReasoningEffort": {"kind": "low"}},
    ],
    "references": [
        reference("ficha-tarjeta-platinum-1", 2.1, 2),
        reference("ficha-tarjeta-oro-1", 3.4, 1),
        reference("ficha-tarjeta-platinum-2", 1.2, 2),
    ],
}


def retriever_answering(status: int, body: dict, seen: list[httpx.Request]) -> AgenticRetriever:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    async def token() -> str:
        return "search-token"

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return AgenticRetriever(ENDPOINT, http=http, token_provider=token, model="gpt-4.1-mini")


async def test_planned_subqueries_and_references_become_the_retrieval():
    retrieval = await retriever_answering(200, PLANNED_RESPONSE, []).search("¿Diferencia entre Oro y Platinum?", top=2)

    assert retrieval.mode == "agentic"
    assert retrieval.subqueries == ["requisitos tarjeta Oro", "requisitos tarjeta Platinum"]
    assert [(chunk.id, chunk.doc_id, chunk.section, chunk.reranker_score) for chunk in retrieval.chunks] == [
        ("ficha-tarjeta-oro-1", "ficha-tarjeta-oro", "1", 3.4),
        ("ficha-tarjeta-platinum-1", "ficha-tarjeta-platinum", "1", 2.1),
    ]
    assert retrieval.chunks[0].content == "Contenido de ficha-tarjeta-oro-1"
    assert (retrieval.usage.tokens_in, retrieval.usage.tokens_out) == (1200, 80)
    assert retrieval.usage.cost_usd == pytest.approx(1200 * 0.40 / 1e6 + 80 * 1.60 / 1e6)


async def test_retrieve_asks_the_knowledge_base_to_plan_over_bank_docs():
    seen: list[httpx.Request] = []

    await retriever_answering(200, PLANNED_RESPONSE, seen).search("¿Diferencia entre Oro y Platinum?", top=8)

    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == f"/knowledgebases('{KNOWLEDGE_BASE}')/retrieve"
    assert request.url.params["api-version"] == AGENTIC_API_VERSION == "2026-08-01-preview"
    assert request.headers["Authorization"] == "Bearer search-token"
    body = json.loads(request.content)
    assert body["messages"] == [{"role": "user", "content": [{"type": "text", "text": "¿Diferencia entre Oro y Platinum?"}]}]
    assert body["retrievalReasoningEffort"] == {"kind": "low"}
    assert body["outputMode"] == "extractiveData"
    assert body["includeActivity"] is True
    assert body["maxOutputDocuments"] == 8
    (source,) = body["knowledgeSourceParams"]
    assert source["kind"] == "searchIndex"
    assert source["knowledgeSourceName"] == KNOWLEDGE_SOURCE
    assert source["includeReferences"] is True
    assert source["includeReferenceSourceData"] is True


@pytest.mark.parametrize("status", [206, 403])
async def test_anything_but_a_complete_retrieval_fails_loud(status):
    with pytest.raises(httpx.HTTPStatusError):
        await retriever_answering(status, PLANNED_RESPONSE, []).search("¿Oro o Platinum?", top=8)


def test_knowledge_source_returns_every_field_a_chunk_is_built_from():
    definition = knowledge_source_definition("bank-docs")

    assert (definition["name"], definition["kind"]) == (KNOWLEDGE_SOURCE, "searchIndex")
    parameters = definition["searchIndexParameters"]
    assert parameters["searchIndexName"] == "bank-docs"
    assert parameters["semanticConfigurationName"] == "default"
    assert {field["name"] for field in parameters["sourceDataFields"]} == set(Chunk.model_fields) - {"reranker_score"}


def test_knowledge_base_plans_with_the_chat_deployment_and_no_key():
    definition = knowledge_base_definition("https://aoai.example", "gpt-4.1-mini")

    assert definition["name"] == KNOWLEDGE_BASE
    assert definition["knowledgeSources"] == [{"name": KNOWLEDGE_SOURCE}]
    assert definition["models"] == [
        {
            "kind": "azureOpenAI",
            "azureOpenAIParameters": {
                "resourceUri": "https://aoai.example",
                "deploymentId": "gpt-4.1-mini",
                "modelName": "gpt-4.1-mini",
            },
        }
    ]
    assert "apiKey" not in json.dumps(definition)
