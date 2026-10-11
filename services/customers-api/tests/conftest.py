import time
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from bank_contracts.auth import PERSONA_AUDIENCE, PERSONA_ISSUER, PERSONAS
from bank_contracts.models import Grant
from customers_api.main import create_app
from customers_api.store import GrantExists

SECRET = "test-backend-secret"
CUSTOMERS_FIXTURE = Path(__file__).parent / "fixtures" / "customers.json"


def _private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


SIGNING_KEY = _private_key()
FOREIGN_KEY = _private_key()


def make_token(persona: str, *, key=SIGNING_KEY, ttl: int = 3600, **overrides) -> str:
    name, role = PERSONAS[persona]
    now = int(time.time())
    claims = {
        "iss": PERSONA_ISSUER,
        "aud": PERSONA_AUDIENCE,
        "sub": persona,
        "name": name,
        "roles": [role],
        "iat": now,
        "exp": now + ttl,
    } | overrides
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test"})


def bearer(persona: str, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(persona, **kwargs)}"}


class InMemoryStore:
    """Same interface as CosmosStore, for tests."""

    def __init__(self):
        self.grants: dict[str, Grant] = {}
        self.audit_log: list[dict] = []

    def create_grant(self, grant: Grant) -> None:
        if grant.id in self.grants:
            raise GrantExists(grant.id)
        self.grants[grant.id] = grant

    def grants_for_customer(self, customer_id: str) -> list[Grant]:
        return [g for g in self.grants.values() if g.customer_id == customer_id]

    def audit(self, entry: dict) -> None:
        self.audit_log.append(entry)


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def client(store, monkeypatch) -> TestClient:
    public_pem = SIGNING_KEY.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    monkeypatch.setenv("BACKEND_SECRET", SECRET)
    monkeypatch.setenv("CUSTOMERS_PATH", str(CUSTOMERS_FIXTURE))
    monkeypatch.setenv("PERSONA_PUBLIC_KEY_PEM", public_pem.decode())
    return TestClient(create_app(store), headers={"X-Backend-Secret": SECRET})
