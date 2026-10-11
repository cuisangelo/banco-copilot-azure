import hmac
from datetime import UTC, datetime
from pathlib import Path as FilePath
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Path, Request
from fastapi.responses import JSONResponse

from bank_contracts.models import CUSTOMER_ID_PATTERN, CustomerProfile
from bank_contracts.settings import require_env
from customers_api.auth import Persona, PersonaVerifier
from customers_api.store import Store, load_customers

CustomerId = Annotated[str, Path(pattern=CUSTOMER_ID_PATTERN)]


def create_app(store: Store) -> FastAPI:
    backend_secret = require_env("BACKEND_SECRET")
    customers = load_customers(FilePath(require_env("CUSTOMERS_PATH")))
    verifier = PersonaVerifier(require_env("PERSONA_PUBLIC_KEY_PEM"))
    Advisor = Annotated[Persona, Depends(verifier.require("Asesor"))]

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

    return app
