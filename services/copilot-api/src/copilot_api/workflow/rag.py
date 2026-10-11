import time

from agent_framework import Executor, WorkflowContext, handler
from agent_framework.openai import OpenAIEmbeddingClient
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from bank_contracts.models import ChatAnswer
from pydantic import BaseModel

from copilot_api.workflow.escalation import ESCALATION_EXECUTOR_ID, EscalationCase
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn

TOP_K = 5
RERANKER_THRESHOLD = 1.5
DOC_ROUTES = ("procedure", "mixed")

NOT_FOUND_MESSAGE = "No lo encuentro en la documentación vigente. Puedo ayudarte a escalar la consulta."


class Chunk(BaseModel):
    id: str
    doc_id: str
    doc_title: str
    section: str
    content: str
    reranker_score: float


class AzureSearchRetriever:
    """Hybrid (BM25 + vector) query with semantic reranking over the `bank-docs` index."""

    def __init__(self, search: SearchClient, embeddings: OpenAIEmbeddingClient) -> None:
        self._search = search
        self._embeddings = embeddings

    async def search(self, query: str, *, top: int) -> list[Chunk]:
        vector = (await self._embeddings.get_embeddings([query]))[0].vector
        results = await self._search.search(
            search_text=query,
            vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=50, fields="content_vector")],
            query_type="semantic",
            semantic_configuration_name="default",
            select=["id", "doc_id", "doc_title", "section", "content"],
            top=top,
        )
        return [
            Chunk(
                id=result["id"],
                doc_id=result["doc_id"],
                doc_title=result["doc_title"],
                section=result["section"],
                content=result["content"],
                reranker_score=result["@search.reranker_score"],
            )
            async for result in results
        ]


class Rag(Executor):
    def __init__(self, services: Services, *, threshold: float = RERANKER_THRESHOLD) -> None:
        super().__init__(id="rag_agent")
        self._services = services
        self._threshold = threshold

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn | EscalationCase]) -> None:
        if turn.route.route not in DOC_ROUTES:
            await ctx.send_message(turn, target_id="product_agent")
            return
        started = time.perf_counter()
        found = await self._services.retriever.search(turn.route.search_query, top=TOP_K)
        relevant = [chunk for chunk in found if chunk.reranker_score >= self._threshold]
        attacks = (
            await self._services.safety.document_attacks(turn.message, [chunk.content for chunk in relevant])
            if relevant
            else []
        )
        dropped = [chunk.id for chunk, attacked in zip(relevant, attacks, strict=True) if attacked]
        turn.chunks = [chunk for chunk, attacked in zip(relevant, attacks, strict=True) if not attacked]
        if dropped:
            await self._services.store.audit(
                actor=turn.actor,
                event="guardrail_rejection",
                data={"session_id": turn.session_id, "layer": "prompt_shields_documents", "chunk_ids": dropped},
            )
        await emit_trace(
            ctx,
            "rag_agent",
            started,
            {
                "chunks": [{"id": chunk.id, "score": chunk.reranker_score} for chunk in found],
                "threshold": self._threshold,
                "dropped_by_prompt_shields": dropped,
            },
        )
        if not turn.chunks and turn.route.route == "procedure":
            answer = ChatAnswer(status="insufficient", message=NOT_FOUND_MESSAGE)
            await ctx.send_message(
                EscalationCase(turn, answer, reason="no está en la documentación vigente"),
                target_id=ESCALATION_EXECUTOR_ID,
            )
            return
        await ctx.send_message(turn, target_id="product_agent")
