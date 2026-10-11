from agent_framework import CheckpointStorage, Workflow, WorkflowBuilder

from copilot_api.workflow.clarifier import Clarifier
from copilot_api.workflow.customer import Customer
from copilot_api.workflow.input_guard import InputGuard
from copilot_api.workflow.products import Products
from copilot_api.workflow.rag import Rag
from copilot_api.workflow.router import Router
from copilot_api.workflow.turn import Services, Turn

WORKFLOW_NAME = "copilot"


def _needs_clarification(turn: Turn) -> bool:
    return turn.route.route == "missing_context"


def build_workflow(services: Services, checkpoint_storage: CheckpointStorage) -> Workflow:
    input_guard = InputGuard(services)
    router = Router(services)
    clarifier = Clarifier()
    rag = Rag(services)
    products = Products(services)
    customer = Customer(services)
    return (
        WorkflowBuilder(name=WORKFLOW_NAME, start_executor=input_guard, checkpoint_storage=checkpoint_storage)
        .add_edge(input_guard, router)
        .add_edge(router, clarifier, condition=_needs_clarification)
        .add_edge(router, rag, condition=lambda turn: not _needs_clarification(turn))
        .add_edge(rag, products)
        .add_edge(products, customer)
        .build()
    )
