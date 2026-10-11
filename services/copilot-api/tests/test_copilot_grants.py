from datetime import UTC, datetime

import httpx
import pytest
from bank_contracts.models import AccessRequest

from copilot_api.grants import GrantConflict, GrantsClient

DECIDED = AccessRequest(
    id="ar-1",
    customer_id="C-1001",
    fields=["monthly_income"],
    purpose="Evaluar requisitos del hipotecario",
    requested_by="ana",
    status="approved",
    created_at=datetime(2026, 10, 11, tzinfo=UTC),
    decided_by="sofia",
    decided_at=datetime(2026, 10, 11, tzinfo=UTC),
    approved_fields=["monthly_income"],
)


def _client(responder) -> GrantsClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(responder))
    return GrantsClient(apim_base_url="https://apim.example/", subscription_key="sub-key", http=http)


async def test_grant_goes_to_apim_with_the_supervisor_token_and_subscription_key():
    seen = {}

    def responder(request: httpx.Request) -> httpx.Response:
        seen.update(
            url=str(request.url),
            auth=request.headers["Authorization"],
            key=request.headers["Ocp-Apim-Subscription-Key"],
            body=request.read(),
        )
        return httpx.Response(201, json={})

    await _client(responder).create(DECIDED, "supervisor.jwt")

    assert seen["url"] == "https://apim.example/customers-api/grants"
    assert (seen["auth"], seen["key"]) == ("Bearer supervisor.jwt", "sub-key")
    assert AccessRequest.model_validate_json(seen["body"]) == DECIDED


async def test_existing_grant_is_a_conflict():
    with pytest.raises(GrantConflict):
        await _client(lambda request: httpx.Response(409, json={})).create(DECIDED, "supervisor.jwt")


async def test_other_upstream_errors_surface():
    with pytest.raises(httpx.HTTPStatusError):
        await _client(lambda request: httpx.Response(422, json={})).create(DECIDED, "supervisor.jwt")
