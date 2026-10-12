import json
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

import jwt
from agent_framework import ChatResponse, Message
from bank_contracts.models import AccessRequest, CustomerFields, CustomerProfile, FieldsDenied, Product
from pydantic import BaseModel

from copilot_api.grants import GrantConflict
from copilot_api.guards.content_safety import Groundedness
from copilot_api.mcp_bank import ToolFailed
from copilot_api.workflow.llm import Usage
from copilot_api.workflow.rag import Retrieval, RetrievalMode
from copilot_api.workflow.relevance import RelevanceVerdict


class FakeChatClient:
    """Chat client that answers each structured-output call from a per-schema script.

    A script entry is either a fixed model instance or a callable that receives the prompt text.
    """

    def __init__(self, script: dict[type[BaseModel], BaseModel | Callable[[str], BaseModel]] | None = None) -> None:
        # The final relevance check passes unless a test scripts it.
        self.script = {RelevanceVerdict: RelevanceVerdict(verdict="answers", missing=None), **(script or {})}
        self.prompts: list[str] = []

    async def get_response(self, messages, *, stream: bool = False, options: Any = None, **kwargs: Any) -> ChatResponse:
        schema = options["response_format"]
        prompt = "\n".join(message.text for message in messages)
        self.prompts.append(prompt)
        entry = self.script[schema]
        value = entry(prompt) if callable(entry) else entry
        return ChatResponse(
            messages=[Message("assistant", [json.dumps(value.model_dump(mode="json"))])],
            response_format=schema,
            usage_details={"input_token_count": 1000, "output_token_count": 200},
        )


def ungrounded_detail(text: str, segment: str) -> dict:
    """The `ungroundedDetails` entry detectGroundedness returns for `segment` within `text`."""
    offset = text.index(segment)
    return {
        "text": segment,
        "offset": {"utf8": len(text[:offset].encode()), "utf16": offset, "codePoint": offset},
        "length": {"utf8": len(segment.encode()), "utf16": len(segment), "codePoint": len(segment)},
        "reason": None,
    }


class FakeSafety:
    def __init__(self, *, user_attack: bool = False, attacked_snippets: tuple[str, ...] = (), ungrounded: bool = False):
        self._user_attack = user_attack
        self._attacked = attacked_snippets
        self._ungrounded = ungrounded

    async def user_attack(self, text: str) -> bool:
        return self._user_attack

    async def document_attacks(self, user_text: str, documents: list[str]) -> list[bool]:
        return [any(snippet in document for snippet in self._attacked) for document in documents]

    async def groundedness(self, text: str, sources: list[str], *, query: str) -> Groundedness:
        return Groundedness(1.0, [text]) if self._ungrounded else Groundedness(0.0, [])


PROFILES = {
    "C-1001": CustomerProfile(
        customer_id="C-1001", segment="personas", income_type="dependiente", products=["CTA-SUELDO"], customer_tenure_months=40
    ),
    "C-1002": CustomerProfile(
        customer_id="C-1002", segment="preferente", income_type="independiente", products=["TC-ORO"], customer_tenure_months=12
    ),
    "C-1003": CustomerProfile(
        customer_id="C-1003", segment="personas", income_type="dependiente", products=[], customer_tenure_months=60
    ),
    "C-1004": CustomerProfile(
        customer_id="C-1004", segment="personas", income_type="dependiente", products=["TC-ORO", "SEGURO-VIDA"],
        customer_tenure_months=24,
    ),
}
LEVEL2_VALUES = {
    "C-1001": {"monthly_income": 1_850_000, "current_debt": 420_000, "payment_behavior": "al_dia", "employment_tenure_months": 18},
    "C-1002": {"monthly_income": 2_730_000, "current_debt": 0, "payment_behavior": "atraso_30", "employment_tenure_months": 7},
    "C-1003": {"monthly_income": 1_200_000, "current_debt": 90_000, "payment_behavior": "al_dia", "employment_tenure_months": 30},
    "C-1004": {"monthly_income": 950_000, "current_debt": 0, "payment_behavior": "al_dia", "employment_tenure_months": 24},
}
PRODUCTS = {
    "TC-ORO": Product(
        id="TC-ORO", name="Tarjeta Oro", category="credit_card", annual_rate_pct=28.5, monthly_fee_clp=4500,
        requirements=["Renta líquida mínima de $800.000"], valid_from="2026-01-01",
    ),
    "TC-PLATINUM": Product(
        id="TC-PLATINUM", name="Tarjeta Platinum", category="credit_card", annual_rate_pct=26.0, monthly_fee_clp=7900,
        requirements=["Renta líquida mínima de $1.500.000"], valid_from="2026-01-01",
    ),
}


class FakeBank:
    """mcp-bank stand-in; `grants` plays customers-api's live grants: {(advisor, customer): {fields}}."""

    def __init__(self) -> None:
        self.grants: dict[tuple[str, str], set[str]] = {}
        self.calls: list[tuple[str, dict]] = []
        self.actor: str | None = None

    async def get_product(self, product_id: str) -> Product:
        self.calls.append(("get_product", {"product_id": product_id}))
        if product_id not in PRODUCTS:
            raise ToolFailed("product not found")
        return PRODUCTS[product_id]

    async def list_products(self, category: str | None) -> list[Product]:
        self.calls.append(("list_products", {"category": category}))
        return [product for product in PRODUCTS.values() if category in (None, product.category)]

    async def compare_products(self, product_ids: list[str]) -> list[Product]:
        self.calls.append(("compare_products", {"product_ids": product_ids}))
        return [PRODUCTS[product_id] for product_id in product_ids]

    async def get_customer_profile(self, customer_id: str) -> CustomerProfile:
        self.calls.append(("get_customer_profile", {"customer_id": customer_id}))
        if customer_id not in PROFILES:
            raise ToolFailed("customer not found")
        return PROFILES[customer_id]

    async def get_customer_fields(self, customer_id: str, fields: list[str]) -> CustomerFields | FieldsDenied:
        self.calls.append(("get_customer_fields", {"customer_id": customer_id, "fields": list(fields)}))
        if customer_id not in PROFILES:
            raise ToolFailed("customer not found")
        granted = self.grants.get((self.actor, customer_id), set())
        denied = [field for field in fields if field not in granted]
        if denied:
            return FieldsDenied(customer_id=customer_id, denied_fields=denied)
        return CustomerFields(
            customer_id=customer_id,
            values={field: LEVEL2_VALUES[customer_id][field] for field in fields},
            grant_id=f"g-{customer_id}",
        )


def fake_connect(bank: FakeBank):
    """connect_bank stand-in: binds the fake to the persona in the token, as customers-api would."""

    @asynccontextmanager
    async def connect(token: str | None):
        bank.actor = jwt.decode(token, options={"verify_signature": False})["sub"] if token else None
        yield bank

    return connect


class FakeGrants:
    """customers-api POST /grants stand-in that also makes the grant visible to FakeBank."""

    def __init__(self, bank: FakeBank) -> None:
        self._bank = bank
        self.created: list[tuple[str, str]] = []

    async def create(self, request: AccessRequest, token: str) -> None:
        if any(request_id == request.id for request_id, _ in self.created):
            raise GrantConflict(request.id)
        approver = jwt.decode(token, options={"verify_signature": False})["sub"]
        self.created.append((request.id, approver))
        key = (request.requested_by, request.customer_id)
        self._bank.grants[key] = self._bank.grants.get(key, set()) | set(request.approved_fields)


class FakeRetriever:
    def __init__(self, chunks, *, mode: RetrievalMode = "hybrid", subqueries: list[str] | None = None, usage: Usage | None = None):
        self.chunks = chunks
        self.queries: list[str] = []
        self._mode, self._subqueries, self._usage = mode, subqueries or [], usage

    async def search(self, query: str, *, top: int) -> Retrieval:
        self.queries.append(query)
        return Retrieval(mode=self._mode, chunks=self.chunks[:top], subqueries=self._subqueries, usage=self._usage)
