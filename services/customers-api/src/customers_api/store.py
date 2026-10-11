import json
from pathlib import Path
from typing import Literal, Protocol

from pydantic import ConfigDict, TypeAdapter

from bank_contracts.models import CustomerProfile, Grant


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
