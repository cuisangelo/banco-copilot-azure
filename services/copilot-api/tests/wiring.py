from copilot_api.store import InMemoryStore
from copilot_api.workflow.llm import Llm
from copilot_api.workflow.turn import Services
from fakes import FakeChatClient, FakeSafety


def make_services(**overrides) -> Services:
    defaults = {
        "llm": Llm(FakeChatClient(), model="gpt-4.1-mini"),
        "safety": FakeSafety(),
        "store": InMemoryStore(),
    }
    return Services(**{**defaults, **overrides})
