import os
import pickle

import pytest
from agent_framework import InMemoryCheckpointStorage, WorkflowCheckpoint
from agent_framework._workflows._checkpoint_encoding import encode_checkpoint_value
from agent_framework.exceptions import WorkflowCheckpointException
from bank_contracts.models import EscalationDecision

from copilot_api.store import dump_checkpoint, load_checkpoint
from copilot_api.workflow.composer import DraftClaim
from copilot_api.workflow.customer import CustomerPlan
from copilot_api.workflow.escalation import EscalationOutcome
from copilot_api.workflow.graph import build_workflow
from copilot_api.workflow.products import ProductCall, ProductPlan
from copilot_api.workflow.turn import HistoryEntry, Turn, TurnResult
from fakes import FakeBank, FakeRetriever
from test_copilot_workflow import CIRCULAR, FICHA, TENURE, composed, route, scripted
from wiring import make_services


async def checkpoints_of_a_turn_that_pauses_twice() -> list[WorkflowCheckpoint]:
    """Access request -> approval -> resume -> contradiction -> escalation decision: every node and both pauses."""
    bank = FakeBank()
    bank.actor = "ana"
    llm = scripted(
        route("mixed"),
        ProductPlan(calls=[ProductCall(tool="get_product", product_id="TC-ORO")]),
        CustomerPlan(fields=["employment_tenure_months"], purpose="Verificar antigüedad laboral para el hipotecario"),
        composed(
            DraftClaim(text="12 meses", citation_ids=["S1"], attribute=TENURE, value="12 meses", customer_meets=True),
            DraftClaim(text="24 meses", citation_ids=["S2"], attribute=TENURE, value="24 meses", customer_meets=False),
        ),
    )
    services = make_services(llm=llm, retriever=FakeRetriever([FICHA, CIRCULAR]), bank=bank)
    storage = InMemoryCheckpointStorage()
    history = [HistoryEntry(question="¿Y la antigüedad?", answer="Depende del producto.", customer_id="C-1001")]
    turn = Turn(session_id="s-1", message="¿C-1001 cumple?", customer_id="C-1001", actor="ana", history=history)

    first = build_workflow(services, storage)
    paused = [event async for event in first.run(turn, stream=True)]
    request = next(e.data.answer.access_request for e in paused if isinstance(e.data, TurnResult))
    bank.grants[("ana", "C-1001")] = {"employment_tenure_months"}
    decided = request.model_copy(update={"status": "approved", "approved_fields": ["employment_tenure_months"]})
    second = build_workflow(services, storage)
    resumed = [
        event
        async for event in second.run(
            responses={request.id: decided}, checkpoint_id=first.get_last_checkpoint_id(), stream=True
        )
    ]
    (escalated,) = [e.data.answer for e in resumed if isinstance(e.data, TurnResult)]
    assert escalated.status == "contradiction"
    third = build_workflow(services, storage)
    decided_escalation = [
        event
        async for event in third.run(
            responses={escalated.escalation.id: EscalationDecision(approve=True)},
            checkpoint_id=second.get_last_checkpoint_id(),
            stream=True,
        )
    ]
    assert any(isinstance(event.data, EscalationOutcome) for event in decided_escalation)
    return await storage.list_checkpoints(workflow_name="copilot")


async def test_every_checkpoint_the_workflow_writes_survives_restricted_decoding():
    checkpoints = await checkpoints_of_a_turn_that_pauses_twice()

    restored = [load_checkpoint(dump_checkpoint(checkpoint)) for checkpoint in checkpoints]

    assert [c.checkpoint_id for c in restored] == [c.checkpoint_id for c in checkpoints]
    turns = [(r.state.get("turn"), c.state.get("turn")) for r, c in zip(restored, checkpoints, strict=True)]
    assert any(original is not None for _, original in turns)
    assert all(back == original for back, original in turns)


class _Exploit:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    def __reduce__(self):
        return os.system, (f"touch {self.marker}",)


async def test_checkpoint_smuggling_a_callable_is_refused_without_running_it(tmp_path):
    marker = tmp_path / "pwned"
    (checkpoint,) = (await checkpoints_of_a_turn_that_pauses_twice())[:1]
    tampered = dump_checkpoint(checkpoint)
    tampered["state"]["turn"] = encode_checkpoint_value(_Exploit(str(marker)))

    with pytest.raises(WorkflowCheckpointException) as refused:
        load_checkpoint(tampered)

    assert isinstance(refused.value.__cause__, pickle.UnpicklingError)
    assert not marker.exists()
