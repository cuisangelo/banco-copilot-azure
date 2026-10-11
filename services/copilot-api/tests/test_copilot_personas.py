import jwt
from bank_contracts.auth import PERSONA_AUDIENCE, PERSONA_ISSUER


def test_unknown_persona_is_rejected(client):
    response = client.post("/demo/session", json={"persona": "mallory"})

    assert response.status_code == 422


def test_issued_token_verifies_against_published_jwks(client):
    session = client.post("/demo/session", json={"persona": "sofia"})
    assert session.status_code == 200
    body = session.json()
    assert body["name"] == "Sofía"
    assert body["role"] == "Supervisor"

    jwks = jwt.PyJWKSet.from_dict(client.get("/.well-known/jwks.json").json())
    kid = jwt.get_unverified_header(body["token"])["kid"]
    claims = jwt.decode(
        body["token"],
        key=jwks[kid].key,
        algorithms=["RS256"],
        audience=PERSONA_AUDIENCE,
        issuer=PERSONA_ISSUER,
    )

    assert claims["sub"] == "sofia"
    assert claims["roles"] == ["Supervisor"]
    assert claims["exp"] - claims["iat"] == 3600
