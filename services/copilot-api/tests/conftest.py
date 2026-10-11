import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from copilot_api.main import create_app
from copilot_api.personas import PersonaIssuer
from wiring import make_deps


@pytest.fixture(scope="session")
def private_key_pem() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def personas(private_key_pem) -> PersonaIssuer:
    return PersonaIssuer(private_key_pem=private_key_pem, key_id="test-key")


@pytest.fixture
def client(personas) -> TestClient:
    return TestClient(create_app(make_deps(personas)))
