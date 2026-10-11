from dataclasses import dataclass
from typing import Literal

from bank_contracts.auth import PERSONAS, Role
from fastapi import FastAPI
from pydantic import BaseModel

from copilot_api.personas import PersonaIssuer

PersonaKey = Literal[tuple(PERSONAS)]


class SessionRequest(BaseModel):
    persona: PersonaKey


class SessionResponse(BaseModel):
    token: str
    name: str
    role: Role


@dataclass
class Deps:
    personas: PersonaIssuer


def create_app(deps: Deps) -> FastAPI:
    app = FastAPI(title="copilot-api")

    @app.post("/demo/session")
    def demo_session(body: SessionRequest) -> SessionResponse:
        token, name, role = deps.personas.issue(body.persona)
        return SessionResponse(token=token, name=name, role=role)

    @app.get("/.well-known/jwks.json")
    def jwks() -> dict:
        return deps.personas.jwks()

    return app
