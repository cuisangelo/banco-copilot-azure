import pytest
from pydantic import ValidationError

from bank_contracts.models import AccessRequestCreate, ChatRequest, Claim
from bank_contracts.settings import require_env


def test_chat_request_rejects_customer_id_without_prefix():
    with pytest.raises(ValidationError):
        ChatRequest(session_id="s1", message="hola", customer_id="1042")


def test_chat_request_accepts_valid_customer_id():
    assert ChatRequest(session_id="s1", message="hola", customer_id="C-1042").customer_id == "C-1042"


def test_claim_requires_a_citation():
    with pytest.raises(ValidationError):
        Claim(text="Requiere liquidación de sueldo", citation_ids=[])


def test_access_request_rejects_short_purpose():
    with pytest.raises(ValidationError):
        AccessRequestCreate(customer_id="C-1042", fields=["monthly_income"], purpose="corto")


def test_access_request_rejects_empty_fields():
    with pytest.raises(ValidationError):
        AccessRequestCreate(customer_id="C-1042", fields=[], purpose="verificar requisitos hipotecario")


def test_require_env_raises_when_missing(monkeypatch):
    monkeypatch.delenv("BANK_TEST_VAR", raising=False)
    with pytest.raises(RuntimeError, match="BANK_TEST_VAR is required"):
        require_env("BANK_TEST_VAR")
