import time
from dataclasses import dataclass

import jwt
from bank_contracts.auth import PERSONA_AUDIENCE, PERSONA_ISSUER, PERSONA_TTL_SECONDS, PERSONAS, Role
from cryptography.hazmat.primitives import serialization


@dataclass(frozen=True)
class Principal:
    sub: str
    name: str
    roles: list[Role]

    def has_role(self, role: Role) -> bool:
        return role in self.roles


class InvalidToken(Exception):
    pass


class PersonaIssuer:
    """Signs demo persona tokens and verifies the ones presented back to copilot-api."""

    def __init__(self, *, private_key_pem: str, key_id: str) -> None:
        self._private_key = serialization.load_pem_private_key(private_key_pem.encode(), password=None)
        self._public_key = self._private_key.public_key()
        self._key_id = key_id

    def issue(self, persona: str) -> tuple[str, str, Role]:
        name, role = PERSONAS[persona]
        now = int(time.time())
        claims = {
            "iss": PERSONA_ISSUER,
            "aud": PERSONA_AUDIENCE,
            "sub": persona,
            "name": name,
            "roles": [role],
            "iat": now,
            "exp": now + PERSONA_TTL_SECONDS,
        }
        token = jwt.encode(claims, self._private_key, algorithm="RS256", headers={"kid": self._key_id})
        return token, name, role

    def jwks(self) -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self._public_key, as_dict=True)
        return {"keys": [{**jwk, "kid": self._key_id, "use": "sig", "alg": "RS256"}]}

    def verify(self, token: str) -> Principal:
        try:
            claims = jwt.decode(
                token,
                key=self._public_key,
                algorithms=["RS256"],
                audience=PERSONA_AUDIENCE,
                issuer=PERSONA_ISSUER,
                options={"require": ["exp", "iat", "sub"]},
            )
        except jwt.InvalidTokenError as error:
            raise InvalidToken(str(error)) from error
        return Principal(sub=claims["sub"], name=claims["name"], roles=claims["roles"])
