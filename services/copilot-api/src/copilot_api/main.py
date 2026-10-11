import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx
import openai
from agent_framework import Workflow, WorkflowEvent
from agent_framework.openai import OpenAIChatCompletionClient, OpenAIEmbeddingClient
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential
from azure.search.documents.aio import SearchClient
from bank_contracts.auth import PERSONAS, Role
from bank_contracts.models import (
    AccessDecision,
    AccessRequest,
    AccessRequestStatus,
    ChatRequest,
    EscalationDecision,
    EscalationDraft,
    ErrorEvent,
)
from bank_contracts.settings import require_env
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry import trace
from pydantic import BaseModel

from copilot_api.grants import GrantConflict, GrantsClient
from copilot_api.guards.content_safety import ContentSafety
from copilot_api.guards.rate_limit import RateLimiter
from copilot_api.guards.token_cap import TokenCap, TokenCapExceeded, utc_day
from copilot_api.mcp_bank import McpBankTools
from copilot_api.personas import InvalidToken, PersonaIssuer, Principal
from copilot_api.store import AlreadyDecided, CosmosStore, InMemoryStore, PendingCheckpoint, SessionRecord
from copilot_api.telemetry import configure_telemetry
from copilot_api.workflow.escalation import EscalationOutcome
from copilot_api.workflow.graph import WORKFLOW_NAME, build_workflow
from copilot_api.workflow.llm import Llm
from copilot_api.workflow.rag import AzureSearchRetriever
from copilot_api.workflow.trace import TRACE_EVENT_TYPE
from copilot_api.workflow.turn import BankTools, HistoryEntry, Retriever, Safety, Services, Turn, TurnResult

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

PersonaKey = Literal[tuple(PERSONAS)]
HISTORY_TURNS = 10
RATE_LIMIT_PER_MINUTE = 10
COGNITIVE_SERVICES_SCOPE = "https://cognitiveservices.azure.com/.default"
OMITTED_ANSWER = "(respuesta con datos sensibles del cliente; no se conserva en el historial)"


class SessionRequest(BaseModel):
    persona: PersonaKey


class SessionResponse(BaseModel):
    token: str
    name: str
    role: Role


@dataclass
class Deps:
    personas: PersonaIssuer
    store: InMemoryStore | CosmosStore
    llm: Llm
    safety: Safety
    retriever: Retriever
    connect_bank: Callable[[str | None], AbstractAsyncContextManager[BankTools]]
    grants: GrantsClient
    token_cap: TokenCap
    rate_limiter: RateLimiter
    cors_origin: str


@dataclass(frozen=True)
class Caller:
    principal: Principal | None
    token: str | None

    @property
    def sub(self) -> str | None:
        return self.principal.sub if self.principal else None


class ApiError(Exception):
    def __init__(self, status_code: int, event: ErrorEvent) -> None:
        self.status_code = status_code
        self.event = event


def _sse(name: str, model: BaseModel) -> str:
    return f"event: {name}\ndata: {model.model_dump_json()}\n\n"


def _error_code(error: Exception) -> Literal["upstream", "internal"]:
    return "upstream" if isinstance(error, openai.APIError | httpx.HTTPError) else "internal"


def create_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="copilot-api")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[deps.cors_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    bearer = HTTPBearer(auto_error=False)

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return JSONResponse(error.event.model_dump(), status_code=error.status_code)

    def caller(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Caller:
        if credentials is None:
            return Caller(principal=None, token=None)
        try:
            return Caller(principal=deps.personas.verify(credentials.credentials), token=credentials.credentials)
        except InvalidToken as error:
            raise ApiError(401, ErrorEvent(code="unauthorized", message="Token inválido o vencido.")) from error

    def persona(who: Caller = Depends(caller)) -> Caller:
        if who.principal is None:
            raise ApiError(401, ErrorEvent(code="unauthorized", message="Esta acción requiere una persona."))
        return who

    def supervisor(who: Caller = Depends(persona)) -> Caller:
        if not who.principal.has_role("Supervisor"):
            raise HTTPException(403, "Solo un Supervisor puede gestionar solicitudes de acceso.")
        return who

    def rate_limited(request: Request) -> None:
        if not deps.rate_limiter.allow(request.client.host):
            raise ApiError(429, ErrorEvent(code="rate_limited", message="Demasiadas consultas; espera un minuto."))

    async def within_token_cap() -> None:
        try:
            await deps.token_cap.check(utc_day())
        except TokenCapExceeded as error:
            message = "Se alcanzó el tope diario de uso del copiloto. Vuelve a intentarlo mañana."
            raise ApiError(503, ErrorEvent(code="token_cap", message=message)) from error

    def owned(session: SessionRecord | None, who: Caller) -> SessionRecord:
        if session is None:
            raise HTTPException(404, "Sesión inexistente.")
        if session.owner != who.sub:
            raise HTTPException(403, "La sesión pertenece a otra persona.")
        return session

    async def discard_checkpoints(session_id: str) -> None:
        storage = deps.store.checkpoint_storage(session_id)
        for checkpoint in await storage.list_checkpoints(workflow_name=WORKFLOW_NAME):
            await storage.delete(checkpoint.checkpoint_id)

    def workflow_for(session_id: str, bank: BankTools) -> Workflow:
        services = Services(llm=deps.llm, safety=deps.safety, store=deps.store, retriever=deps.retriever, bank=bank)
        return build_workflow(services, deps.store.checkpoint_storage(session_id))

    def stream_turn(
        session: SessionRecord,
        who: Caller,
        question: str,
        customer_id: str | None,
        run: Callable[[Workflow], AsyncIterator[WorkflowEvent]],
    ) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            tokens, result, pending = 0, None, None
            try:
                async with deps.connect_bank(who.token) as bank:
                    workflow = workflow_for(session.session_id, bank)
                    async for event in run(workflow):
                        if event.type == TRACE_EVENT_TYPE:
                            tokens += event.data.tokens_in + event.data.tokens_out
                            yield _sse("trace", event.data)
                        elif event.type == "output" and isinstance(event.data, TurnResult):
                            result = event.data
                        elif event.type == "request_info":
                            kind = "escalation" if isinstance(event.data, EscalationDraft) else "access"
                            pending = (kind, event.request_id)
                    checkpoint_id = workflow.get_last_checkpoint_id()
                if result is None:
                    raise RuntimeError("workflow finished without an answer")
            except Exception as error:
                logger.exception("turn failed for session %s", session.session_id)
                message = "No pude completar la consulta por una falla interna; inténtalo nuevamente."
                yield _sse("error", ErrorEvent(code=_error_code(error), message=message))
                return
            finally:
                await deps.token_cap.record(utc_day(), tokens)
            answer_text = OMITTED_ANSWER if result.level2_values else result.answer.message
            entry = HistoryEntry(question=question, answer=answer_text, customer_id=customer_id)
            session.history = [*session.history, entry][-HISTORY_TURNS:]
            session.pending = (
                PendingCheckpoint(
                    kind=pending[0],
                    request_id=pending[1],
                    checkpoint_id=checkpoint_id,
                    question=question,
                    customer_id=customer_id,
                )
                if pending
                else None
            )
            await deps.store.save_session(session)
            if pending is None:
                await discard_checkpoints(session.session_id)
            yield _sse("answer", result.answer)

        return StreamingResponse(events(), media_type="text/event-stream")

    @app.post("/demo/session")
    def demo_session(body: SessionRequest) -> SessionResponse:
        token, name, role = deps.personas.issue(body.persona)
        return SessionResponse(token=token, name=name, role=role)

    @app.get("/.well-known/jwks.json")
    def jwks() -> dict:
        return deps.personas.jwks()

    @app.post("/chat", dependencies=[Depends(rate_limited)])
    async def chat(body: ChatRequest, who: Caller = Depends(caller)) -> StreamingResponse:
        await within_token_cap()
        existing = await deps.store.get_session(body.session_id)
        session = owned(existing, who) if existing else SessionRecord(session_id=body.session_id, owner=who.sub)
        session.pending = None
        turn = Turn(
            session_id=body.session_id,
            message=body.message,
            customer_id=body.customer_id,
            actor=who.sub,
            history=[entry for entry in session.history if entry.customer_id == body.customer_id],
        )
        return stream_turn(
            session, who, body.message, body.customer_id, lambda workflow: workflow.run(turn, stream=True)
        )

    @app.post("/sessions/{session_id}/resume", dependencies=[Depends(rate_limited)])
    async def resume(session_id: str, who: Caller = Depends(persona)) -> StreamingResponse:
        session = owned(await deps.store.get_session(session_id), who)
        pending = session.pending
        if pending is None or pending.kind != "access":
            raise HTTPException(409, "La sesión no tiene una solicitud de acceso pendiente.")
        decided = await deps.store.get_access_request(pending.request_id)
        if decided.status == "pending":
            raise HTTPException(409, "La solicitud de acceso aún no tiene decisión.")
        await within_token_cap()
        return stream_turn(
            session,
            who,
            pending.question,
            pending.customer_id,
            lambda workflow: workflow.run(
                responses={pending.request_id: decided}, checkpoint_id=pending.checkpoint_id, stream=True
            ),
        )

    @app.post("/escalations/{escalation_id}/decision")
    async def decide_escalation(escalation_id: str, body: EscalationDecision, who: Caller = Depends(caller)) -> dict:
        session = owned(await deps.store.find_session_by_escalation(escalation_id), who)
        outcomes = []
        async with deps.connect_bank(who.token) as bank:
            workflow = workflow_for(session.session_id, bank)
            async for event in workflow.run(
                responses={escalation_id: body}, checkpoint_id=session.pending.checkpoint_id, stream=True
            ):
                if event.type == "output" and isinstance(event.data, EscalationOutcome):
                    outcomes.append(event.data)
        session.pending = None
        await deps.store.save_session(session)
        await discard_checkpoints(session.session_id)
        (outcome,) = outcomes
        return {"discarded": True} if outcome.discarded else {"ticket_id": outcome.ticket_id}

    @app.get("/access-requests", dependencies=[Depends(supervisor)])
    async def list_access_requests(status: AccessRequestStatus | None = None) -> list[AccessRequest]:
        return await deps.store.list_access_requests(status)

    @app.get("/access-requests/{request_id}")
    async def get_access_request(request_id: str, who: Caller = Depends(persona)) -> AccessRequest:
        request = await deps.store.get_access_request(request_id)
        if request is None:
            raise HTTPException(404, "Solicitud inexistente.")
        if request.requested_by != who.sub and not who.principal.has_role("Supervisor"):
            raise HTTPException(403, "Solo el solicitante o un Supervisor pueden ver esta solicitud.")
        return request

    @app.post("/access-requests/{request_id}/decision")
    async def decide_access_request(
        request_id: str, body: AccessDecision, who: Caller = Depends(supervisor)
    ) -> AccessRequest:
        request = await deps.store.get_access_request(request_id)
        if request is None:
            raise HTTPException(404, "Solicitud inexistente.")
        if request.requested_by == who.sub:
            raise HTTPException(403, "Un Supervisor no puede aprobar su propia solicitud.")
        if request.status != "pending":
            raise HTTPException(409, "La solicitud ya fue decidida.")
        if not set(body.approved_fields) <= set(request.fields):
            raise HTTPException(422, "Solo se pueden aprobar campos solicitados.")
        approved = [field for field in request.fields if field in body.approved_fields]
        status: AccessRequestStatus = (
            "rejected" if not approved else "approved" if approved == request.fields else "partially_approved"
        )
        decided = request.model_copy(
            update={
                "status": status,
                "approved_fields": approved,
                "decided_by": who.sub,
                "decided_at": datetime.now(UTC),
            }
        )
        try:
            if approved:
                await deps.grants.create(decided, who.token)
            await deps.store.decide_access_request(decided)
        except (GrantConflict, AlreadyDecided) as error:
            raise HTTPException(409, "La solicitud ya fue decidida.") from error
        with tracer.start_as_current_span("access_request.decision") as span:
            span.set_attribute("access_request.status", status)
            await deps.store.audit(
                actor=who.sub,
                event="access_decision",
                data={"access_request_id": request_id, "status": status, "approved_fields": approved},
            )
        return decided

    return app


def deps_from_env() -> Deps:
    """Production wiring: every setting is required and every Azure call authenticates with the managed identity."""
    credential = DefaultAzureCredential()
    openai_endpoint = require_env("AZURE_OPENAI_ENDPOINT")
    api_version = require_env("AZURE_OPENAI_API_VERSION")
    chat_deployment = require_env("AZURE_OPENAI_CHAT_DEPLOYMENT")
    chat = OpenAIChatCompletionClient(
        model=chat_deployment, azure_endpoint=openai_endpoint, api_version=api_version, credential=credential
    )
    embeddings = OpenAIEmbeddingClient(
        model=require_env("AZURE_OPENAI_EMBEDDING_DEPLOYMENT"),
        azure_endpoint=openai_endpoint,
        api_version=api_version,
        credential=credential,
    )
    search = SearchClient(require_env("SEARCH_ENDPOINT"), require_env("SEARCH_INDEX"), credential)

    async def cognitive_services_token() -> str:
        return (await credential.get_token(COGNITIVE_SERVICES_SCOPE)).token

    http = httpx.AsyncClient(timeout=30)
    cosmos = CosmosClient(require_env("COSMOS_ENDPOINT"), credential=credential)
    store = CosmosStore(cosmos.get_database_client(require_env("COSMOS_DATABASE")))
    mcp_bank_url = require_env("MCP_BANK_URL")
    return Deps(
        personas=PersonaIssuer(
            private_key_pem=require_env("PERSONA_PRIVATE_KEY_PEM"), key_id=require_env("PERSONA_KEY_ID")
        ),
        store=store,
        llm=Llm(chat, model=chat_deployment),
        safety=ContentSafety(
            endpoint=require_env("CONTENT_SAFETY_ENDPOINT"), http=http, token_provider=cognitive_services_token
        ),
        retriever=AzureSearchRetriever(search, embeddings),
        connect_bank=lambda token: McpBankTools.connect(mcp_bank_url, token=token),
        grants=GrantsClient(
            apim_base_url=require_env("APIM_BASE_URL"),
            subscription_key=require_env("APIM_SUBSCRIPTION_KEY"),
            http=http,
        ),
        token_cap=TokenCap(store, daily_cap=int(require_env("DAILY_TOKEN_CAP"))),
        rate_limiter=RateLimiter(per_minute=RATE_LIMIT_PER_MINUTE),
        cors_origin=require_env("CORS_ORIGIN"),
    )


def build_app() -> FastAPI:
    """Entry point for `uvicorn --factory copilot_api.main:build_app`."""
    configure_telemetry(require_env("APPLICATIONINSIGHTS_CONNECTION_STRING"))
    return create_app(deps_from_env())
