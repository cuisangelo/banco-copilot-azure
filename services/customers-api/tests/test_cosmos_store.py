from datetime import UTC, datetime, timedelta

import pytest
from azure.cosmos.exceptions import CosmosResourceExistsError

from bank_contracts.models import Grant
from customers_api.store import CosmosStore, GrantExists


class FakeContainer:
    """Mimics Cosmos semantics the store relies on: id unique per partition, queries scoped to one partition."""

    def __init__(self, partition_key: str):
        self.partition_key = partition_key
        self.items: list[dict] = []

    def create_item(self, body: dict) -> dict:
        if any(i["id"] == body["id"] and i[self.partition_key] == body[self.partition_key] for i in self.items):
            raise CosmosResourceExistsError(status_code=409, message="Conflict")
        self.items.append(body)
        return body

    def query_items(self, query: str, parameters: list[dict], partition_key: str):
        assert parameters == [{"name": "@customer_id", "value": partition_key}]
        return [i for i in self.items if i[self.partition_key] == partition_key]


class FakeDatabase:
    def __init__(self):
        self.containers = {"grants": FakeContainer("customer_id"), "audit": FakeContainer("actor")}

    def get_container_client(self, name: str) -> FakeContainer:
        return self.containers[name]


def make_grant(grant_id: str = "ar-1", customer_id: str = "C-1042", minutes: int = 30) -> Grant:
    return Grant(
        id=grant_id,
        access_request_id=grant_id,
        customer_id=customer_id,
        advisor_sub="ana",
        fields=["monthly_income"],
        purpose="verificar requisitos del crédito hipotecario",
        approved_by="sofia",
        expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
    )


@pytest.fixture
def database() -> FakeDatabase:
    return FakeDatabase()


def test_grant_ttl_matches_expiry(database):
    CosmosStore(database).create_grant(make_grant(minutes=30))

    [item] = database.containers["grants"].items
    assert 1790 <= item["ttl"] <= 1800


def test_duplicate_grant_raises_grant_exists(database):
    store = CosmosStore(database)
    store.create_grant(make_grant())

    with pytest.raises(GrantExists):
        store.create_grant(make_grant())


def test_grants_for_customer_reads_only_that_partition(database):
    store = CosmosStore(database)
    store.create_grant(make_grant("ar-1", "C-1042"))
    store.create_grant(make_grant("ar-2", "C-2001"))

    assert [g.id for g in store.grants_for_customer("C-1042")] == ["ar-1"]


def test_audit_entries_get_unique_ids(database):
    store = CosmosStore(database)
    store.audit({"actor": "ana", "action": "read_profile"})
    store.audit({"actor": "ana", "action": "read_profile"})

    ids = [i["id"] for i in database.containers["audit"].items]
    assert len(set(ids)) == 2
