from typing import Literal

PERSONA_ISSUER = "banco-copilot-demo"
PERSONA_AUDIENCE = "banco-copilot"
PERSONA_TTL_SECONDS = 3600
Role = Literal["Asesor", "Supervisor"]
PERSONAS: dict[str, tuple[str, Role]] = {
    "ana": ("Ana", "Asesor"),
    "bruno": ("Bruno", "Asesor"),
    "sofia": ("Sofía", "Supervisor"),
}
# Claims: iss, aud, sub (persona key), name, roles: [Role], iat, exp. Algorithm RS256, header kid.
