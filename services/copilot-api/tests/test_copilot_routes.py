import json
from datetime import UTC, datetime

import httpx
import jwt
import pytest
from bank_contracts.models import AccessRequest

from copilot_api.main import create_app
from copilot_api.mcp_bank import McpBankTools
from copilot_api.workflow.composer import ComposerOutput, DraftClaim
from copilot_api.workflow.customer import CustomerPlan
from copilot_api.workflow.products import ProductCall, ProductPlan
from copilot_api.workflow.router import RouteDecision
from fakes import FakeChatClient, FakeRetriever, FakeSafety
from test_copilot_mcp_adapter import build_server
from test_copilot_workflow import CIRCULAR, FICHA
from wiring import make_deps

INCOME = "1850000"


def parse_sse(body: str) -> list[tuple[str, dict]]:
    events = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


class Api:
    def __init__(self, deps, personas):
        self.deps = deps
        self.personas = personas
        self._http = httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(deps)), base_url="http://test")

    def token(self, persona: str) -> str:
        return self.personas.issue(persona)[0]

    async def request(self, method: str, path: str, persona: str | None = None, **kwargs) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token(persona)}"} if persona else {}
        return await self._http.request(method, path, headers=headers, **kwargs)

    async def chat(self, message: str, persona: str | None = None, customer_id: str | None = None, session_id="s-1"):
        body = {"session_id": session_id, "message": message, "customer_id": customer_id}
        response = await self.request("POST", "/chat", persona, json=body)
        assert response.status_code == 200, response.text
        return parse_sse(response.text)

    async def resume(self, persona: str, session_id="s-1") -> httpx.Response:
        return await self.request("POST", f"/sessions/{session_id}/resume", persona)


def answer(events) -> dict:
    answers = [data for name, data in events if name == "answer"]
    assert len(answers) == 1 and events[-1][0] == "answer"
    return answers[0]


def customer_script(fields: list[str], message: str = f"La renta mensual informada es {INCOME}.") -> FakeChatClient:
    def compose(prompt: str) -> ComposerOutput:
        cited = "S2" if "monthly_income" in prompt.split("Fuentes:")[-1] else "S1"
        return ComposerOutput(message=message, requirements=[DraftClaim(text=message, citation_ids=[cited])], steps=[])

    return FakeChatClient({
        RouteDecision: lambda prompt: RouteDecision(route="customer", search_query="¿cumple para el hipotecario?"),
        CustomerPlan: CustomerPlan(fields=fields, purpose="Evaluar requisitos del crédito hipotecario"),
        ComposerOutput: compose,
    })


@pytest.fixture
def api(personas):
    def build(**overrides) -> Api:
        return Api(make_deps(personas, **overrides), personas)

    return build


async def test_chat_streams_traces_then_a_single_answer(api):
    client = FakeChatClient({
        RouteDecision: RouteDecision(route="procedure", search_query="antigüedad hipotecario"),
        ComposerOutput: ComposerOutput(
            message="Se exigen 12 meses.", requirements=[DraftClaim(text="12 meses", citation_ids=["S1"])], steps=[]
        ),
    })
    app = api(chat_client=client, retriever=FakeRetriever([FICHA]))

    events = await app.chat("¿antigüedad laboral para el hipotecario?")

    assert answer(events)["status"] == "ok"
    assert {name for name, _ in events[:-1]} == {"trace"}
    assert [data["node"] for name, data in events if name == "trace"][:2] == ["input_guard", "router"]


def traces(events) -> dict[str, dict]:
    return {data["node"]: data for name, data in events if name == "trace"}


async def test_trace_events_carry_cost_chunks_and_guardrails(api):
    client = FakeChatClient({
        RouteDecision: RouteDecision(route="procedure", search_query="antigüedad hipotecario"),
        ComposerOutput: ComposerOutput(
            message="Se exigen 12 meses.", requirements=[DraftClaim(text="12 meses", citation_ids=["S1"])], steps=[]
        ),
    })
    app = api(chat_client=client, retriever=FakeRetriever([FICHA]), safety=FakeSafety(ungrounded=True))

    nodes = traces(await app.chat("¿antigüedad laboral para el hipotecario?"))

    assert nodes["router"]["cost_usd"] == pytest.approx(1000 * 0.40 / 1e6 + 200 * 1.60 / 1e6)
    assert nodes["router"]["data"] == {"route": "procedure"}
    assert nodes["rag_agent"]["data"]["chunks"] == [
        {"id": FICHA.id, "doc_id": FICHA.doc_id, "section": FICHA.section, "score": FICHA.reranker_score, "content": FICHA.content}
    ]
    assert nodes["verifier"]["data"]["guardrail"] == "groundedness"
    assert "guardrail" not in nodes["input_guard"]["data"]


async def test_customer_trace_reports_the_denial_without_values(api):
    app = api(chat_client=customer_script(["monthly_income"]))

    events = await app.chat("¿Renta de C-1001?", "ana", "C-1001")

    customer = traces(events)["customer_agent"]["data"]
    assert customer["authz.decision"] == "denied"
    assert customer["tool_calls"] == [
        {"tool": "get_customer_profile", "arguments": {"customer_id": "C-1001"}, "result_kind": "ok"},
        {
            "tool": "get_customer_fields",
            "arguments": {"customer_id": "C-1001", "fields": ["monthly_income"]},
            "result_kind": "denied",
        },
    ]
    assert INCOME not in json.dumps([data for name, data in events if name == "trace"])


async def test_rut_typed_by_the_advisor_is_still_answered(api):
    client = FakeChatClient({
        RouteDecision: RouteDecision(route="procedure", search_query="bloqueo de tarjeta"),
        ComposerOutput: ComposerOutput(
            message="Bloquéala desde el canal.", requirements=[], steps=[DraftClaim(text="Llamar", citation_ids=["S1"])]
        ),
    })
    app = api(chat_client=client, retriever=FakeRetriever([FICHA]))

    events = await app.chat("Cliente 12.345.678-9 con tarjeta 4111111111111111 quiere bloquearla")

    assert answer(events)["status"] == "ok"


async def test_eleventh_request_in_a_minute_is_rate_limited(api):
    app = api()
    statuses = [
        (await app.request("POST", "/chat", json={"session_id": "s-9", "message": ""})).status_code for _ in range(11)
    ]

    assert statuses[:10] == [422] * 10
    assert statuses[10] == 429


async def test_token_cap_returns_503_and_usage_is_recorded(api):
    client = FakeChatClient({RouteDecision: RouteDecision(route="out_of_scope", search_query="bitcoin")})
    app = api(chat_client=client, daily_token_cap=1200)

    await app.chat("¿qué opinas de bitcoin?")
    blocked = await app.request("POST", "/chat", json={"session_id": "s-1", "message": "¿y ethereum?"})

    assert blocked.status_code == 503
    assert blocked.json()["code"] == "token_cap"


async def test_invalid_token_is_unauthorized(api):
    response = await api()._http.post(
        "/chat", headers={"Authorization": "Bearer not-a-jwt"}, json={"session_id": "s-1", "message": "hola"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


async def test_another_persona_cannot_use_someone_elses_session(api):
    client = FakeChatClient({RouteDecision: RouteDecision(route="out_of_scope", search_query="x")})
    app = api(chat_client=client)
    await app.chat("¿bitcoin?", persona="ana")

    response = await app.request("POST", "/chat", "bruno", json={"session_id": "s-1", "message": "¿bitcoin?"})

    assert response.status_code == 403


async def test_access_request_flow_from_denial_to_resumed_answer(api):
    app = api(chat_client=customer_script(["monthly_income", "current_debt"]))

    first = answer(await app.chat("¿C-1001 cumple para el hipotecario?", "ana", "C-1001"))
    assert first["status"] == "access_required"
    request_id = first["access_request"]["id"]

    assert (await app.resume("ana")).status_code == 409
    pending = await app.request("GET", "/access-requests", "sofia", params={"status": "pending"})
    assert [item["id"] for item in pending.json()] == [request_id]
    assert (await app.request("GET", "/access-requests", "ana")).status_code == 403
    assert (await app.request("GET", f"/access-requests/{request_id}", "bruno")).status_code == 403
    assert (await app.request("GET", f"/access-requests/{request_id}", "ana")).status_code == 200
    assert (await app.request("GET", f"/access-requests/{request_id}", "sofia")).status_code == 200
    assert (await app.request("GET", "/access-requests/nope", "sofia")).status_code == 404

    path = f"/access-requests/{request_id}/decision"
    assert (await app.request("POST", path, "ana", json={"approved_fields": ["monthly_income"]})).status_code == 403
    decided = await app.request("POST", path, "sofia", json={"approved_fields": ["monthly_income"]})
    assert decided.status_code == 200
    assert (decided.json()["status"], decided.json()["decided_by"]) == ("partially_approved", "sofia")
    assert app.deps.grants.created == [(request_id, "sofia")]
    again = await app.request("POST", path, "sofia", json={"approved_fields": ["monthly_income"]})
    assert again.status_code == 409
    assert len(app.deps.grants.created) == 1

    assert (await app.resume("bruno")).status_code == 403
    resumed = await app.resume("ana")
    final = answer(parse_sse(resumed.text))
    assert final["status"] == "ok"
    assert INCOME in final["message"]
    assert "deuda vigente: no autorizado — verificar con el cliente" in final["message"]
    assert (await app.resume("ana")).status_code == 409


async def test_supervisor_cannot_approve_their_own_request(api):
    app = api()
    request = AccessRequest(
        id="ar-1",
        customer_id="C-1001",
        fields=["monthly_income"],
        purpose="Revisar renta para hipotecario",
        requested_by="sofia",
        status="pending",
        created_at=datetime.now(UTC),
    )
    await app.deps.store.create_access_request(request)

    response = await app.request("POST", "/access-requests/ar-1/decision", "sofia", json={"approved_fields": []})

    assert response.status_code == 403


async def test_listing_without_status_returns_every_request(api):
    app = api(chat_client=customer_script(["monthly_income"]))
    await app.chat("¿C-1001 cumple?", "ana", "C-1001")
    request_id = (await app.request("GET", "/access-requests", "sofia")).json()[0]["id"]
    await app.request("POST", f"/access-requests/{request_id}/decision", "sofia", json={"approved_fields": []})

    everything = (await app.request("GET", "/access-requests", "sofia")).json()
    rejected = (await app.request("GET", "/access-requests", "sofia", params={"status": "rejected"})).json()
    pending = (await app.request("GET", "/access-requests", "sofia", params={"status": "pending"})).json()

    assert [item["status"] for item in everything] == ["rejected"]
    assert [item["id"] for item in rejected] == [request_id]
    assert pending == []
    assert app.deps.grants.created == []


async def test_escalation_decision_returns_a_ticket_to_its_owner_only(api):
    client = FakeChatClient({
        RouteDecision: RouteDecision(route="procedure", search_query="antigüedad"),
        ComposerOutput: ComposerOutput(
            message="Las fuentes difieren.",
            requirements=[
                DraftClaim(text="12 meses", citation_ids=["S1"], attribute="antigüedad", value="12 meses"),
                DraftClaim(text="24 meses", citation_ids=["S2"], attribute="antigüedad", value="24 meses"),
            ],
            steps=[],
        ),
    })
    app = api(chat_client=client, retriever=FakeRetriever([FICHA, CIRCULAR]))
    escalation_id = answer(await app.chat("¿antigüedad laboral hipotecario?", "ana"))["escalation"]["id"]
    path = f"/escalations/{escalation_id}/decision"

    assert (await app.request("POST", path, "bruno", json={"approve": True})).status_code == 403
    approved = await app.request("POST", path, "ana", json={"approve": True})
    assert approved.status_code == 200
    assert approved.json()["ticket_id"].startswith("TCK-")
    assert (await app.request("POST", path, "ana", json={"approve": True})).status_code == 404
    assert app.deps.store.audit_log[-1]["event"] == "escalation_decision"


async def test_each_request_reaches_mcp_with_its_own_persona(api):
    seen: list[dict] = []
    server = build_server(seen)
    mcp_app = server.streamable_http_app()

    def connect(token: str | None):
        http = httpx.AsyncClient(transport=httpx.ASGITransport(app=mcp_app), base_url="http://localhost:8000")
        return McpBankTools.connect("http://localhost:8000/mcp", token=token, http_client=http, backoff_seconds=0)

    client = FakeChatClient({
        RouteDecision: RouteDecision(route="product", search_query="tarjeta Oro"),
        ProductPlan: ProductPlan(calls=[ProductCall(tool="get_product", product_id="TC-ORO")]),
        ComposerOutput: ComposerOutput(
            message="Mantención $4.500.", requirements=[DraftClaim(text="$4.500", citation_ids=["S1"])], steps=[]
        ),
    })
    app = api(chat_client=client, connect_bank=connect)

    async with server.session_manager.run():
        await app.chat("¿mantención Oro?", "ana", session_id="s-ana")
        await app.chat("¿mantención Oro?", "bruno", session_id="s-bruno")
        await app.chat("¿mantención Oro?", None, session_id="s-anon")

    subs = [
        jwt.decode(call["authorization"].removeprefix("Bearer "), options={"verify_signature": False})["sub"]
        if call["authorization"]
        else None
        for call in seen
    ]
    assert subs == ["ana", "bruno", None]


async def test_expired_grant_requires_a_new_request_and_history_keeps_no_values(api):
    """Review Focus 1: level-2 values never come back from history once the grant lapses."""
    client = customer_script(["monthly_income"])
    app = api(chat_client=client)
    app.deps.bank.grants[("ana", "C-1001")] = {"monthly_income"}

    first = answer(await app.chat("¿Renta de C-1001?", "ana", "C-1001"))
    assert first["status"] == "ok" and INCOME in first["message"]

    del app.deps.bank.grants[("ana", "C-1001")]
    prompts_before = len(client.prompts)
    second = answer(await app.chat("¿Renta de C-1001?", "ana", "C-1001"))

    assert second["status"] == "access_required"
    assert second["access_request"]["fields"] == ["monthly_income"]
    assert not any(INCOME in prompt for prompt in client.prompts[prompts_before:])
    session = await app.deps.store.get_session("s-1")
    assert INCOME not in session.model_dump_json()


async def test_switching_customer_drops_the_previous_customers_context(api):
    """Review Focus 2: nothing about C-1001 reaches the turn about C-1002."""
    client = customer_script([], message="Cliente segmento {segment}.")
    app = api(chat_client=client)

    await app.chat("¿Qué le ofrezco a C-1001?", "ana", "C-1001")
    prompts_before = len(client.prompts)
    second = answer(await app.chat("¿Qué le ofrezco a C-1002?", "ana", "C-1002"))

    later_prompts = "\n".join(client.prompts[prompts_before:])
    assert "C-1001" not in later_prompts
    assert "C-1001" not in json.dumps(second)
    assert [call for call in app.deps.bank.calls if call[1].get("customer_id") == "C-1001"] == [
        ("get_customer_profile", {"customer_id": "C-1001"})
    ]
