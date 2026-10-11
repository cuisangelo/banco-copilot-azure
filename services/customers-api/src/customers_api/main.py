import hmac
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from bank_contracts.models import (
    CUSTOMER_ID_PATTERN,
    AccessRequest,
    CustomerFields,
    CustomerProfile,
    FieldsDenied,
    Grant,
    Level2Field,
)
from bank_contracts.settings import require_env
from customers_api.auth import Persona, PersonaVerifier
from customers_api.grants import InvalidDecision, denied_fields, grant_from_decision, live_grants
from customers_api.store import CosmosStore, GrantExists, Store, load_customers

CustomerId = Annotated[str, Path(pattern=CUSTOMER_ID_PATTERN)]


class FieldsRequest(BaseModel):
    fields: list[Level2Field] = Field(min_length=1)


def create_app(store: Store) -> FastAPI:
    backend_secret = require_env("BACKEND_SECRET")
    customers = load_customers(FilePath(require_env("CUSTOMERS_PATH")))
    verifier = PersonaVerifier(require_env("PERSONA_PUBLIC_KEY_PEM"))
    Advisor = Annotated[Persona, Depends(verifier.require("Asesor"))]
    Supervisor = Annotated[Persona, Depends(verifier.require("Supervisor"))]

    app = FastAPI(title="customers-api")

    @app.middleware("http")
    async def require_backend_secret(request: Request, call_next):
        received = request.headers.get("X-Backend-Secret", "")
        if not hmac.compare_digest(received.encode(), backend_secret.encode()):
            return JSONResponse({"detail": "missing or invalid backend secret"}, status_code=401)
        return await call_next(request)

    def audit(actor: str, action: str, customer_id: str, **details) -> None:
        store.audit(
            {
                "actor": actor,
                "action": action,
                "customer_id": customer_id,
                "at": datetime.now(UTC).isoformat(),
                **details,
            }
        )

    @app.get("/customers/{customer_id}/profile")
    def get_profile(customer_id: CustomerId, persona: Advisor) -> CustomerProfile:
        if customer_id not in customers:
            raise HTTPException(404, "customer not found")
        audit(persona.sub, "read_profile", customer_id)
        return customers[customer_id].profile()

    @app.post("/customers/{customer_id}/fields", responses={403: {"model": FieldsDenied}})
    def get_fields(customer_id: CustomerId, body: FieldsRequest, persona: Advisor) -> CustomerFields:
        if customer_id not in customers:
            raise HTTPException(404, "customer not found")
        requested = list(dict.fromkeys(body.fields))
        live = live_grants(store.grants_for_customer(customer_id), persona.sub, datetime.now(UTC))
        denied = denied_fields(requested, live)
        if denied:
            audit(persona.sub, "read_fields", customer_id, fields=requested, grant_ids=[], outcome="denied")
            return JSONResponse(
                FieldsDenied(customer_id=customer_id, denied_fields=denied).model_dump(), status_code=403
            )
        used = [g.id for g in live if set(g.fields) & set(requested)]
        audit(persona.sub, "read_fields", customer_id, fields=requested, grant_ids=used, outcome="allowed")
        record = customers[customer_id]
        return CustomerFields(
            customer_id=customer_id,
            values={field: getattr(record, field) for field in requested},
            grant_id=",".join(used),
        )

    @app.post("/grants", status_code=201)
    def create_grant(request: AccessRequest, persona: Supervisor) -> Grant:
        if request.requested_by == persona.sub:
            raise HTTPException(403, "a supervisor cannot approve their own request")
        if request.customer_id not in customers:
            raise HTTPException(404, "customer not found")
        try:
            grant = grant_from_decision(request, persona.sub, datetime.now(UTC))
        except InvalidDecision as error:
            raise HTTPException(422, str(error)) from error
        try:
            store.create_grant(grant)
        except GrantExists as error:
            raise HTTPException(409, "a grant already exists for this access request") from error
        audit(persona.sub, "create_grant", grant.customer_id, fields=grant.fields, grant_ids=[grant.id])
        return grant

    return app


def app_from_env() -> FastAPI:
    return create_app(CosmosStore.from_env())
