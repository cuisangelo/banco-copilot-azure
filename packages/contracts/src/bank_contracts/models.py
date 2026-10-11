from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ProductCategory = Literal["account", "credit_card", "consumer_loan", "mortgage"]
Level2Field = Literal["monthly_income", "current_debt", "payment_behavior", "employment_tenure_months"]
LEVEL2_FIELDS: tuple[Level2Field, ...] = ("monthly_income", "current_debt", "payment_behavior", "employment_tenure_months")
ChatStatus = Literal["ok", "clarification", "insufficient", "contradiction", "rejected", "access_required"]
AccessRequestStatus = Literal["pending", "approved", "partially_approved", "rejected", "expired"]
CUSTOMER_ID_PATTERN = r"^C-\d{4}$"
GRANT_MINUTES = 30


class Product(BaseModel):
    id: str
    name: str
    category: ProductCategory
    annual_rate_pct: float | None
    monthly_fee_clp: int | None
    requirements: list[str]
    valid_from: date


class CustomerProfile(BaseModel):
    """Level 1 data: available to any Asesor once the customer is identified."""
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    segment: Literal["personas", "preferente", "pyme"]
    income_type: Literal["dependiente", "independiente"]
    products: list[str]
    customer_tenure_months: int


class CustomerFields(BaseModel):
    """Level 2 values, returned only for fields covered by a live grant."""
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    values: dict[Level2Field, int | str]
    grant_id: str


class FieldsDenied(BaseModel):
    """Body of the 403 returned by customers-api when any requested field lacks a live grant."""
    customer_id: str
    denied_fields: list[Level2Field]


class AccessRequestCreate(BaseModel):
    customer_id: str = Field(pattern=CUSTOMER_ID_PATTERN)
    fields: list[Level2Field] = Field(min_length=1)
    purpose: str = Field(min_length=10, max_length=300)


class AccessRequest(AccessRequestCreate):
    id: str
    requested_by: str
    status: AccessRequestStatus
    created_at: datetime
    decided_by: str | None = None
    decided_at: datetime | None = None
    approved_fields: list[Level2Field] = []


class AccessDecision(BaseModel):
    """Empty approved_fields means reject."""
    approved_fields: list[Level2Field]


class Grant(BaseModel):
    id: str
    access_request_id: str
    customer_id: str
    advisor_sub: str
    fields: list[Level2Field]
    purpose: str
    approved_by: str
    expires_at: datetime


class Citation(BaseModel):
    id: str
    kind: Literal["doc", "product", "customer"]
    ref: str          # "ficha-hipotecario §2", "producto:TC-ORO", "cliente:C-1042 monthly_income"
    snippet: str


class Claim(BaseModel):
    text: str
    citation_ids: list[str] = Field(min_length=1)


class EscalationDraft(BaseModel):
    id: str
    area: str
    summary: str
    evidence: list[Citation]


class EscalationDecision(BaseModel):
    approve: bool


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    customer_id: str | None = Field(default=None, pattern=CUSTOMER_ID_PATTERN)


class ChatAnswer(BaseModel):
    status: ChatStatus
    message: str
    requirements: list[Claim] = []
    steps: list[Claim] = []
    citations: list[Citation] = []
    access_request: AccessRequest | None = None
    escalation: EscalationDraft | None = None


class TraceEvent(BaseModel):
    node: str
    duration_ms: int
    data: dict           # never contains level-2 values; field names only
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0


class ErrorEvent(BaseModel):
    code: Literal["token_cap", "rate_limited", "upstream", "unauthorized", "internal"]
    message: str


class FeedbackCreate(BaseModel):
    # Part of a Cosmos document id, which rejects "/", "#", "?" and "\".
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    turn_index: int = Field(ge=0)           # position of the turn in the session, 0-based
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=500)
    answer_status: ChatStatus


class Feedback(FeedbackCreate):
    id: str
    actor: str                               # persona sub or "anonymous"
    created_at: datetime
