import time

from agent_framework import Executor, WorkflowContext, handler
from bank_contracts.models import ChatAnswer

from copilot_api.workflow.trace import emit_trace
from copilot_api.workflow.turn import Services, Turn, TurnResult

ATTACK_MESSAGE = "No puedo procesar esta consulta: contiene instrucciones que intentan alterar mis reglas."


class InputGuard(Executor):
    def __init__(self, services: Services) -> None:
        super().__init__(id="input_guard")
        self._services = services

    @handler
    async def run(self, turn: Turn, ctx: WorkflowContext[Turn, TurnResult]) -> None:
        started = time.perf_counter()
        attack = await self._services.safety.user_attack(turn.message)
        await emit_trace(ctx, "input_guard", started, {"layer": "prompt_shields_user", "attack_detected": attack})
        if attack:
            await self._services.store.audit(
                actor=turn.actor,
                event="guardrail_rejection",
                data={"session_id": turn.session_id, "layer": "prompt_shields_user"},
            )
            await ctx.yield_output(TurnResult(ChatAnswer(status="rejected", message=ATTACK_MESSAGE)))
            return
        await ctx.send_message(turn)
