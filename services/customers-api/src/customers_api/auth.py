from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from fastapi import HTTPException, Request

from bank_contracts.auth import PERSONA_AUDIENCE, PERSONA_ISSUER, Role


@dataclass(frozen=True)
class Persona:
    sub: str
    roles: tuple[str, ...]


class PersonaVerifier:
    def __init__(self, public_key_pem: str):
        self._public_key = load_pem_public_key(public_key_pem.encode())

    def verify(self, request: Request) -> Persona:
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise HTTPException(401, "missing bearer token")
        try:
            claims = jwt.decode(
                token,
                self._public_key,
                algorithms=["RS256"],
                audience=PERSONA_AUDIENCE,
                issuer=PERSONA_ISSUER,
                options={"require": ["iss", "aud", "sub", "iat", "exp"]},
            )
        except jwt.InvalidTokenError as error:
            raise HTTPException(401, "invalid token") from error
        roles = claims.get("roles")
        if not isinstance(roles, list):
            raise HTTPException(401, "invalid token")
        return Persona(sub=claims["sub"], roles=tuple(roles))

    def require(self, role: Role):
        def dependency(request: Request) -> Persona:
            persona = self.verify(request)
            if role not in persona.roles:
                raise HTTPException(403, f"role {role} required")
            return persona

        return dependency
