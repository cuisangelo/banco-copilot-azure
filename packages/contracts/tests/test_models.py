import pytest
from pydantic import ValidationError

from bank_contracts.models import AccessRequestCreate, ChatRequest, Claim, Feedback, FeedbackCreate
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


def test_feedback_rejects_negative_turn_index():
    with pytest.raises(ValidationError):
        FeedbackCreate(session_id="s1", turn_index=-1, rating="up", answer_status="ok")


def test_feedback_rejects_comment_over_500_characters():
    with pytest.raises(ValidationError):
        FeedbackCreate(session_id="s1", turn_index=0, rating="down", comment="x" * 501, answer_status="ok")


def test_feedback_extends_the_create_payload_with_actor_and_time():
    feedback = Feedback(
        session_id="s1",
        turn_index=0,
        rating="up",
        answer_status="ok",
        id="feedback:anonymous:s1:0",
        actor="anonymous",
        created_at="2026-10-11T23:00:00Z",
    )
    assert feedback.comment is None
