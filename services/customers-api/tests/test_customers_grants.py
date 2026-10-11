from datetime import UTC, datetime, timedelta

import pytest
from conftest import bearer

from bank_contracts.models import GRANT_MINUTES, Grant

FIELDS = "/customers/C-1042/fields"
C1042_LEVEL2_VALUES = ["1450000", "3215500", "al_dia"]


def decided_request(
    *,
    request_id: str = "ar-1",
    customer_id: str = "C-1042",
    requested_by: str = "ana",
    fields: list[str] = ("monthly_income", "current_debt"),
    approved_fields: list[str] = ("monthly_income",),
    status: str = "partially_approved",
) -> dict:
    return {
        "id": request_id,
        "customer_id": customer_id,
        "fields": list(fields),
        "purpose": "verificar requisitos del crédito hipotecario",
        "requested_by": requested_by,
        "status": status,
        "created_at": datetime.now(UTC).isoformat(),
        "decided_by": "sofia",
        "decided_at": datetime.now(UTC).isoformat(),
        "approved_fields": list(approved_fields),
    }


def approve(client, **kwargs):
    return client.post("/grants", json=decided_request(**kwargs), headers=bearer("sofia"))


def read_fields(client, fields, persona="ana", path=FIELDS):
    return client.post(path, json={"fields": fields}, headers=bearer(persona))


# --- POST /grants ---


def test_grant_by_supervisor_is_created(client):
    before = datetime.now(UTC)
    response = approve(client)

    assert response.status_code == 201
    grant = Grant.model_validate(response.json())
    assert grant.access_request_id == "ar-1"
    assert grant.customer_id == "C-1042"
    assert grant.advisor_sub == "ana"
    assert grant.fields == ["monthly_income"]
    assert grant.approved_by == "sofia"
    assert before + timedelta(minutes=GRANT_MINUTES) <= grant.expires_at
    assert grant.expires_at <= datetime.now(UTC) + timedelta(minutes=GRANT_MINUTES)


def test_grant_by_advisor_is_403(client, store):
    response = client.post("/grants", json=decided_request(requested_by="bruno"), headers=bearer("ana"))
    assert response.status_code == 403
    assert store.grants == {}


def test_self_approval_is_403(client, store):
    assert approve(client, requested_by="sofia").status_code == 403
    assert store.grants == {}


def test_second_grant_for_same_request_is_409(client, store):
    assert approve(client).status_code == 201
    assert approve(client, approved_fields=["monthly_income", "current_debt"]).status_code == 409
    assert [g.fields for g in store.grants.values()] == [["monthly_income"]]


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "rejected", "approved_fields": []},
        {"status": "pending", "approved_fields": []},
        {"approved_fields": []},
        {"fields": ["monthly_income"], "approved_fields": ["current_debt"]},
    ],
    ids=["rejected", "pending", "nothing-approved", "approved-not-requested"],
)
def test_grant_from_undecided_or_inconsistent_request_is_422(client, store, overrides):
    assert approve(client, **overrides).status_code == 422
    assert store.grants == {}


def test_grant_for_unknown_customer_is_404(client):
    assert approve(client, customer_id="C-9999").status_code == 404


def test_grant_is_audited(client, store):
    approve(client)

    [entry] = store.audit_log
    assert entry["actor"] == "sofia"
    assert entry["action"] == "create_grant"
    assert entry["fields"] == ["monthly_income"]


# --- POST /customers/{id}/fields ---


def test_fields_without_grant_is_403_listing_fields(client):
    response = read_fields(client, ["monthly_income"])

    assert response.status_code == 403
    assert response.json() == {"customer_id": "C-1042", "denied_fields": ["monthly_income"]}


def test_fields_with_grant_of_another_advisor_is_403(client):
    approve(client, requested_by="bruno")

    response = read_fields(client, ["monthly_income"], persona="ana")

    assert response.status_code == 403
    assert response.json()["denied_fields"] == ["monthly_income"]


def test_fields_with_expired_grant_is_403(client, store):
    store.grants["ar-old"] = Grant(
        id="ar-old",
        access_request_id="ar-old",
        customer_id="C-1042",
        advisor_sub="ana",
        fields=["monthly_income"],
        purpose="verificar requisitos del crédito hipotecario",
        approved_by="sofia",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    assert read_fields(client, ["monthly_income"]).status_code == 403


def test_fields_with_grant_for_another_customer_is_403(client):
    approve(client, customer_id="C-2001")

    assert read_fields(client, ["monthly_income"]).status_code == 403


def test_field_not_approved_is_403_listing_only_that_field(client):
    approve(client)

    response = read_fields(client, ["monthly_income", "current_debt"])

    assert response.status_code == 403
    assert response.json()["denied_fields"] == ["current_debt"]


def test_fields_with_live_grant_returns_only_requested_approved_fields(client):
    approve(client, approved_fields=["monthly_income", "current_debt"])

    response = read_fields(client, ["monthly_income"])

    assert response.status_code == 200
    assert response.json() == {"customer_id": "C-1042", "values": {"monthly_income": 1450000}, "grant_id": "ar-1"}


def test_fields_by_supervisor_is_403(client):
    approve(client)
    assert read_fields(client, ["monthly_income"], persona="sofia").status_code == 403


def test_fields_without_token_is_401(client):
    assert client.post(FIELDS, json={"fields": ["monthly_income"]}).status_code == 401


def test_fields_for_unknown_customer_is_404(client):
    assert read_fields(client, ["monthly_income"], path="/customers/C-9999/fields").status_code == 404


def test_fields_for_malformed_customer_is_422(client):
    assert read_fields(client, ["monthly_income"], path="/customers/1042/fields").status_code == 422


def test_unknown_field_name_is_422(client):
    assert read_fields(client, ["rut"]).status_code == 422


def test_fields_reads_are_audited_with_names_never_values(client, store):
    approve(client)
    read_fields(client, ["monthly_income"])
    read_fields(client, ["current_debt", "payment_behavior"])

    granted, denied = store.audit_log[1:]
    assert granted["action"] == "read_fields"
    assert granted["actor"] == "ana"
    assert granted["fields"] == ["monthly_income"]
    assert granted["grant_ids"] == ["ar-1"]
    assert granted["outcome"] == "allowed"
    assert denied["outcome"] == "denied"
    assert denied["fields"] == ["current_debt", "payment_behavior"]
    logged = repr(store.audit_log)
    assert not [value for value in C1042_LEVEL2_VALUES if value in logged]
