import json

import pytest
from fastapi.testclient import TestClient

from products_api.main import create_app

SECRET = "test-backend-secret"
PRODUCTS = [
    {
        "id": "TC-ORO",
        "name": "Tarjeta Oro",
        "category": "credit_card",
        "annual_rate_pct": 28.5,
        "monthly_fee_clp": 4500,
        "requirements": ["Renta mínima 800.000"],
        "valid_from": "2026-01-01",
    },
    {
        "id": "CTA-SUELDO",
        "name": "Cuenta Sueldo",
        "category": "account",
        "annual_rate_pct": None,
        "monthly_fee_clp": 0,
        "requirements": ["Contrato de trabajo"],
        "valid_from": "2026-01-01",
    },
]


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = tmp_path / "products.json"
    path.write_text(json.dumps(PRODUCTS))
    monkeypatch.setenv("BACKEND_SECRET", SECRET)
    monkeypatch.setenv("PRODUCTS_PATH", str(path))
    return TestClient(create_app(), headers={"X-Backend-Secret": SECRET})


def test_request_without_backend_secret_is_401(client):
    client.headers.pop("X-Backend-Secret")
    assert client.get("/products").status_code == 401


def test_request_with_wrong_backend_secret_is_401(client):
    response = client.get("/products", headers={"X-Backend-Secret": "wrong"})
    assert response.status_code == 401


def test_list_returns_all_products(client):
    response = client.get("/products")
    assert response.status_code == 200
    assert [p["id"] for p in response.json()] == ["TC-ORO", "CTA-SUELDO"]


def test_list_filters_by_category(client):
    response = client.get("/products", params={"category": "account"})
    assert [p["id"] for p in response.json()] == ["CTA-SUELDO"]


def test_list_rejects_unknown_category(client):
    assert client.get("/products", params={"category": "crypto"}).status_code == 422


def test_get_returns_product(client):
    response = client.get("/products/TC-ORO")
    assert response.status_code == 200
    assert response.json()["monthly_fee_clp"] == 4500


def test_get_unknown_product_is_404(client):
    assert client.get("/products/NOPE").status_code == 404


def test_missing_products_path_fails_at_startup(monkeypatch):
    monkeypatch.setenv("BACKEND_SECRET", SECRET)
    monkeypatch.delenv("PRODUCTS_PATH", raising=False)
    with pytest.raises(RuntimeError, match="PRODUCTS_PATH is required"):
        create_app()
