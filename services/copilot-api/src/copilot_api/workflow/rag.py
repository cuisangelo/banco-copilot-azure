import time
from dataclasses import dataclass, field
from typing import Literal

from agent_framework import Executor, WorkflowContext, handler
from agent_framework.openai import OpenAIEmbeddingClient
from azure.search.documents.aio import SearchClient
from azure.search.documents.models import VectorizedQuery
from bank_contracts.models import ChatAnswer
from pydantic import BaseModel

from copilot_api.workflow.escalation import ESCALATION_EXECUTOR_ID, EscalationCase
from copilot_api.workflow.llm import Usage
from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn

# 5 let a comparison fill up with one product's sheet (all Platinum, no Oro), leaving the other
# product's claims ungrounded.
TOP_K = 8
BLOCKED_CONTENT = "[bloqueado por Prompt Shields]"
UNCHECKED_CONTENT = "[bajo el umbral de relevancia: no se verificó ni llegó al modelo]"
RERANKER_THRESHOLD = 1.5
# Relative to the best chunk of the same search. Measured live: for "¿Cómo bloqueo una tarjeta
# extraviada?" the relevant chunks scored 2.47–2.86 and the noise (Oro and Platinum benefits)
# 2.17–2.18; for "¿Diferencia entre Oro y Platinum?" all eight relevant chunks scored 2.24–2.46.
# 0.5 below the best cuts the first noise and keeps the whole second set.
RELEVANCE_MARGIN = 0.5
# Every answering route searches: product sheets carry benefits the products API lacks, and "does
# this customer qualify" needs the bank's rules even when the router labels it customer, not mixed.
# Only procedure turns stop on an empty search; the others still have API data to answer from.
DOC_ROUTES = ("procedure", "mixed", "customer", "product")

NOT_FOUND_MESSAGE = "No lo encuentro en la documentación vigente. Puedo ayudarte a escalar la consulta."


class Chunk(BaseModel):
    id: str
    doc_id: str
    doc_title: str
    section: str
    content: str
    reranker_score: float


RetrievalMode = Literal["hybrid", "agentic"]


@dataclass
class Retrieval:
    """One search: its chunks, the subqueries an agentic plan ran, and the model tokens that plan spent."""

    mode: RetrievalMode
    chunks: list[Chunk]
    subqueries: list[str] = field(default_factory=list)
    usage: Usage | None = None


class AzureSearchRetriever:
    """Hybrid (BM25 + vector) query with semantic reranking over the `bank-docs` index."""

    def __init__(self, search: SearchClient, embeddings: OpenAIEmbeddingClient) -> None:
        self._search = search
        self._embeddings = embeddings

    async def search(self, query: str, *, top: int) -> Retrieval:
        vector = (await self._embeddings.get_embeddings([query]))[0].vector
        results = await self._search.search(
            search_text=query,
            vector_queries=[VectorizedQuery(vector=vector, k_nearest_neighbors=50, fields="content_vector")],
            query_type="semantic",
            semantic_configuration_name="default",
            select=["id", "doc_id", "doc_title", "section", "content"],
            top=top,
        )
        chunks = [
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
        return Retrieval(mode="hybrid", chunks=chunks)


class Rag(Executor):
    def __init__(self, services: Services, *, threshold: float = RERANKER_THRESHOLD) -> None:
        super().__init__(id="rag_agent")
        self._services = services
        self._threshold = threshold

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn | EscalationCase]) -> None:
        if turn.route.route not in DOC_ROUTES:
            await ctx.send_message(turn)
            return
        started = time.perf_counter()
        retrieval = await self._services.retriever.search(turn.route.search_query, top=TOP_K)
        found = retrieval.chunks
        turn.searched = found
        floor = max([self._threshold, *(chunk.reranker_score - RELEVANCE_MARGIN for chunk in found)])
        relevant = [chunk for chunk in found if chunk.reranker_score >= floor]
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
                "chunks": [
                    {
                        "id": chunk.id,
                        "doc_id": chunk.doc_id,
                        "section": chunk.section,
                        "score": chunk.reranker_score,
                        # The inspector shows only text Prompt Shields checked and passed: injected text
                        # reaches neither the model nor the inspector.
                        "content": BLOCKED_CONTENT
                        if chunk.id in dropped
                        else chunk.content
                        if chunk in turn.chunks
                        else UNCHECKED_CONTENT,
                    }
                    for chunk in found
                ],
                "threshold": self._threshold,
                "dropped": dropped,
                "retrieval_mode": retrieval.mode,
            }
            | ({"subqueries": retrieval.subqueries} if retrieval.mode == "agentic" else {})
            | ({"guardrail": "prompt_shields_documents"} if dropped else {}),
            retrieval.usage,
        )
        if not turn.chunks and turn.route.route == "procedure":
            answer = ChatAnswer(status="insufficient", message=NOT_FOUND_MESSAGE)
            await ctx.send_message(
                EscalationCase(turn, answer, reason="no está en la documentación vigente"),
                target_id=ESCALATION_EXECUTOR_ID,
            )
            return
        await ctx.send_message(turn)
