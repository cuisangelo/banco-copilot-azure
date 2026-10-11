import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol
from uuid import uuid4

from azure.cosmos import CosmosClient, DatabaseProxy
from azure.cosmos.exceptions import CosmosResourceExistsError
from azure.identity import DefaultAzureCredential
from pydantic import ConfigDict, TypeAdapter

from bank_contracts.models import CustomerProfile, Grant
from bank_contracts.settings import require_env


class CustomerRecord(CustomerProfile):
    """Level 1 profile plus level 2 values. Level 3 data has no field here, so it cannot be loaded."""

    model_config = ConfigDict(extra="forbid")

    monthly_income: int
    current_debt: int
    payment_behavior: Literal["al_dia", "atraso_30", "atraso_90"]
    employment_tenure_months: int

    def profile(self) -> CustomerProfile:
        return CustomerProfile.model_validate(self.model_dump(include=set(CustomerProfile.model_fields)))


def load_customers(path: Path) -> dict[str, CustomerRecord]:
    records = TypeAdapter(list[CustomerRecord]).validate_python(json.loads(path.read_text()))
    return {r.customer_id: r for r in records}


class GrantExists(Exception):
    pass


class Store(Protocol):
    def create_grant(self, grant: Grant) -> None:
        """Raises GrantExists if a grant with the same id is already stored."""

    def grants_for_customer(self, customer_id: str) -> list[Grant]: ...

    def audit(self, entry: dict) -> None: ...


class CosmosStore:
    def __init__(self, database: DatabaseProxy):
        self._grants = database.get_container_client("grants")
        self._audit = database.get_container_client("audit")

    @classmethod
    def from_env(cls) -> "CosmosStore":
        client = CosmosClient(require_env("COSMOS_ENDPOINT"), credential=DefaultAzureCredential())
        return cls(client.get_database_client(require_env("COSMOS_DATABASE")))

    def create_grant(self, grant: Grant) -> None:
        ttl = int((grant.expires_at - datetime.now(UTC)).total_seconds())
        try:
            self._grants.create_item(grant.model_dump(mode="json") | {"ttl": ttl})
        except CosmosResourceExistsError as error:
            raise GrantExists(grant.id) from error

    def grants_for_customer(self, customer_id: str) -> list[Grant]:
        items = self._grants.query_items(
            "SELECT * FROM c WHERE c.customer_id = @customer_id",
            parameters=[{"name": "@customer_id", "value": customer_id}],
            partition_key=customer_id,
        )
        return [Grant.model_validate(item) for item in items]

    def audit(self, entry: dict) -> None:
        self._audit.create_item(entry | {"id": uuid4().hex})
