import httpx
from bank_contracts.models import AccessRequest


class GrantConflict(Exception):
    pass


class GrantsClient:
    """Records a Supervisor's decision in customers-api through APIM, acting with the Supervisor's own JWT.

    Not an MCP tool: the model never reaches this path.
    """

    def __init__(self, *, apim_base_url: str, subscription_key: str, http: httpx.AsyncClient) -> None:
        self._url = f"{apim_base_url.rstrip('/')}/customers-api/grants"
        self._subscription_key = subscription_key
        self._http = http

    async def create(self, request: AccessRequest, token: str) -> None:
        response = await self._http.post(
            self._url,
            json=request.model_dump(mode="json"),
            headers={"Authorization": f"Bearer {token}", "Ocp-Apim-Subscription-Key": self._subscription_key},
        )
        if response.status_code == 409:
            raise GrantConflict(request.id)
        response.raise_for_status()
