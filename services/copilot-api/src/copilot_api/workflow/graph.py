from agent_framework import CheckpointStorage, Workflow, WorkflowBuilder

from copilot_api.workflow.input_guard import InputGuard
from copilot_api.workflow.turn import Services

WORKFLOW_NAME = "copilot"


def build_workflow(services: Services, checkpoint_storage: CheckpointStorage) -> Workflow:
    input_guard = InputGuard(services)
    return WorkflowBuilder(
        name=WORKFLOW_NAME,
        start_executor=input_guard,
        checkpoint_storage=checkpoint_storage,
    ).build()
