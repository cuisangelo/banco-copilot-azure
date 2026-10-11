"""CosmosStore against the Cosmos DB emulator from compose.yaml.

Opt-in: set COSMOS_EMULATOR_ENDPOINT (e.g. http://localhost:8081) to run; skipped otherwise.
"""

import os
import uuid
from datetime import UTC, datetime

import pytest
from azure.cosmos import PartitionKey
from azure.cosmos.aio import CosmosClient
from bank_contracts.models import AccessRequest

from copilot_api.store import AlreadyDecided, CosmosStore, PendingCheckpoint, SessionRecord
from copilot_api.workflow.graph import build_workflow
from copilot_api.workflow.llm import Llm
from copilot_api.workflow.turn import HistoryEntry, Turn, TurnResult
from fakes import FakeBank
from test_copilot_routes import customer_script
from wiring import make_services

EMULATOR = os.environ.get("COSMOS_EMULATOR_ENDPOINT")
EMULATOR_KEY = "C2y6yDjf5/R+ob0N8A7Cgv30VRDJIWEHLM+4QDU5DE2nQ9nDuVTqobD4b8mGGyPMbIZnqyMsEcaGQy67XIw/Jw=="
CONTAINERS = {
    "sessions": "/session_id",
    "checkpoints": "/session_id",
    "access_requests": "/customer_id",
    "audit": "/actor",
    "usage": "/day",
}

pytestmark = pytest.mark.skipif(not EMULATOR, reason="COSMOS_EMULATOR_ENDPOINT not set")


@pytest.fixture
async def store():
    async with CosmosClient(EMULATOR, credential=EMULATOR_KEY) as client:
        database = await client.create_database(f"copilot-test-{uuid.uuid4().hex[:8]}")
        for name, key in CONTAINERS.items():
            await database.create_container(name, partition_key=PartitionKey(path=key))
        try:
            yield CosmosStore(database)
        finally:
            await client.delete_database(database.id)


def pending_request(request_id: str = "ar-1", requested_by: str = "ana") -> AccessRequest:
    return AccessRequest(
        id=request_id,
        customer_id="C-1001",
        fields=["monthly_income"],
        purpose="Evaluar requisitos del hipotecario",
        requested_by=requested_by,
        status="pending",
        created_at=datetime.now(UTC),
    )


async def test_usage_accumulates_per_day(store):
    assert await store.get_usage("2026-10-11") == 0
    await store.add_usage("2026-10-11", 700)
    await store.add_usage("2026-10-11", 300)
    await store.add_usage("2026-10-12", 5)

    assert await store.get_usage("2026-10-11") == 1000
    assert await store.get_usage("2026-10-12") == 5


async def test_access_requests_round_trip_and_decide_once(store):
    request = pending_request()
    await store.create_access_request(request)
    await store.create_access_request(pending_request("ar-2", "bruno"))

    assert await store.get_access_request("ar-1") == request
    assert await store.get_access_request("missing") is None
    assert {item.id for item in await store.list_access_requests(None)} == {"ar-1", "ar-2"}

    decided = request.model_copy(update={"status": "rejected", "decided_by": "sofia", "decided_at": datetime.now(UTC)})
    await store.decide_access_request(decided)
    with pytest.raises(AlreadyDecided):
        await store.decide_access_request(decided)

    assert [item.id for item in await store.list_access_requests("rejected")] == ["ar-1"]
    assert [item.id for item in await store.list_access_requests("pending")] == ["ar-2"]


async def test_sessions_round_trip_and_are_found_by_escalation(store):
    session = SessionRecord(
        session_id="s-1",
        owner="ana",
        history=[HistoryEntry(question="¿requisitos?", answer="Cédula vigente.", customer_id=None)],
        pending=PendingCheckpoint(
            kind="escalation", request_id="esc-1", checkpoint_id="cp-1", question="¿requisitos?", customer_id=None
        ),
    )
    await store.save_session(session)
    await store.audit(actor=None, event="guardrail_rejection", data={"session_id": "s-1", "layer": "x"})

    assert await store.get_session("s-1") == session
    assert await store.get_session("s-2") is None
    assert await store.find_session_by_escalation("esc-1") == session
    assert await store.find_session_by_escalation("esc-2") is None


async def test_workflow_pauses_and_resumes_through_cosmos_checkpoints(store):
    bank = FakeBank()
    bank.actor = "ana"
    services = make_services(llm=Llm(customer_script(["monthly_income"]), model="gpt-4.1-mini"), bank=bank, store=store)
    storage = store.checkpoint_storage("s-1")
    turn = Turn(session_id="s-1", message="¿Renta de C-1001?", customer_id="C-1001", actor="ana", history=[])

    workflow = build_workflow(services, storage)
    paused = [event async for event in workflow.run(turn, stream=True)]
    request = next(event.data.answer.access_request for event in paused if isinstance(event.data, TurnResult))
    bank.grants[("ana", "C-1001")] = {"monthly_income"}
    decided = request.model_copy(update={"status": "approved", "approved_fields": ["monthly_income"]})

    resumed = build_workflow(services, storage)
    events = [
        event
        async for event in resumed.run(
            responses={request.id: decided}, checkpoint_id=workflow.get_last_checkpoint_id(), stream=True
        )
    ]

    (result,) = [event.data for event in events if isinstance(event.data, TurnResult)]
    assert result.answer.status == "ok"
    assert len(await storage.list_checkpoints(workflow_name="copilot")) >= 1
