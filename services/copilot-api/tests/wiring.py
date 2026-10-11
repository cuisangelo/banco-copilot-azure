from copilot_api.guards.rate_limit import RateLimiter
from copilot_api.guards.token_cap import TokenCap
from copilot_api.main import Deps
from copilot_api.store import InMemoryStore
from copilot_api.workflow.llm import Llm
from copilot_api.workflow.turn import Services
from fakes import FakeBank, FakeChatClient, FakeGrants, FakeRetriever, FakeSafety, fake_connect


def make_services(**overrides) -> Services:
    defaults = {
        "llm": Llm(FakeChatClient(), model="gpt-4.1-mini"),
        "safety": FakeSafety(),
        "store": InMemoryStore(),
        "retriever": FakeRetriever([]),
        "bank": FakeBank(),
    }
    return Services(**{**defaults, **overrides})


def make_deps(
    personas,
    *,
    chat_client: FakeChatClient | None = None,
    retriever: FakeRetriever | None = None,
    safety: FakeSafety | None = None,
    daily_token_cap: int = 1_000_000,
    connect_bank=None,
) -> Deps:
    store, bank = InMemoryStore(), FakeBank()
    deps = Deps(
        personas=personas,
        store=store,
        llm=Llm(chat_client or FakeChatClient(), model="gpt-4.1-mini"),
        safety=safety or FakeSafety(),
        retriever=retriever or FakeRetriever([]),
        connect_bank=connect_bank or fake_connect(bank),
        grants=FakeGrants(bank),
        token_cap=TokenCap(store, daily_cap=daily_token_cap),
        rate_limiter=RateLimiter(per_minute=10),
        cors_origin="https://web.example",
    )
    deps.bank = bank
    return deps
