import json

import pytest
from conftest import CUSTOMERS_FIXTURE, FOREIGN_KEY, InMemoryStore, bearer
from customers_api.main import create_app

from bank_contracts.models import LEVEL2_FIELDS, CustomerProfile

PROFILE = "/customers/C-1042/profile"


def test_without_backend_secret_is_401(client):
    client.headers.pop("X-Backend-Secret")
    assert client.get(PROFILE, headers=bearer("ana")).status_code == 401


def test_without_token_is_401(client):
    assert client.get(PROFILE).status_code == 401


def test_expired_token_is_401(client):
    assert client.get(PROFILE, headers=bearer("ana", ttl=-10)).status_code == 401


def test_token_signed_by_another_key_is_401(client):
    assert client.get(PROFILE, headers=bearer("ana", key=FOREIGN_KEY)).status_code == 401


def test_token_from_another_issuer_is_401(client):
    assert client.get(PROFILE, headers=bearer("ana", iss="someone-else")).status_code == 401


def test_token_for_another_audience_is_401(client):
    assert client.get(PROFILE, headers=bearer("ana", aud="other-api")).status_code == 401


def test_supervisor_role_is_403(client):
    assert client.get(PROFILE, headers=bearer("sofia")).status_code == 403


def test_unknown_customer_is_404(client):
    assert client.get("/customers/C-9999/profile", headers=bearer("ana")).status_code == 404


def test_malformed_customer_id_is_422(client):
    assert client.get("/customers/1042/profile", headers=bearer("ana")).status_code == 422


def test_profile_returns_only_level1_keys(client):
    response = client.get(PROFILE, headers=bearer("ana"))

    assert response.status_code == 200
    body = response.json()
    assert set(body) == set(CustomerProfile.model_fields)
    assert not set(body) & set(LEVEL2_FIELDS)
    assert body["segment"] == "personas"


def test_profile_read_is_audited(client, store):
    client.get(PROFILE, headers=bearer("ana"))

    [entry] = store.audit_log
    assert entry["actor"] == "ana"
    assert entry["action"] == "read_profile"
    assert entry["customer_id"] == "C-1042"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c.update(rut="12.345.678-9"),
        lambda c: c.pop("monthly_income"),
        lambda c: c.update(payment_behavior="excelente"),
    ],
    ids=["extra-key", "missing-key", "bad-payment-behavior"],
)
def test_invalid_customers_file_fails_at_startup(client, tmp_path, monkeypatch, mutate):
    customers = json.loads(CUSTOMERS_FIXTURE.read_text())
    mutate(customers[0])
    path = tmp_path / "customers.json"
    path.write_text(json.dumps(customers))
    monkeypatch.setenv("CUSTOMERS_PATH", str(path))

    with pytest.raises(ValueError):
        create_app(InMemoryStore())


def test_missing_public_key_fails_at_startup(client, monkeypatch):
    monkeypatch.delenv("PERSONA_PUBLIC_KEY_PEM")
    with pytest.raises(RuntimeError, match="PERSONA_PUBLIC_KEY_PEM is required"):
        create_app(InMemoryStore())
