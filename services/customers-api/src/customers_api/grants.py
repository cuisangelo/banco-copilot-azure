from datetime import datetime, timedelta

from bank_contracts.models import GRANT_MINUTES, AccessRequest, Grant, Level2Field


class InvalidDecision(ValueError):
    pass


def grant_from_decision(request: AccessRequest, approver: str, now: datetime) -> Grant:
    if request.status not in ("approved", "partially_approved") or not request.approved_fields:
        raise InvalidDecision("access request is not approved")
    if not set(request.approved_fields) <= set(request.fields):
        raise InvalidDecision("approved fields were not requested")
    # The id is the access request id so the store rejects a second grant for the same request atomically.
    return Grant(
        id=request.id,
        access_request_id=request.id,
        customer_id=request.customer_id,
        advisor_sub=request.requested_by,
        fields=request.approved_fields,
        purpose=request.purpose,
        approved_by=approver,
        expires_at=now + timedelta(minutes=GRANT_MINUTES),
    )


def live_grants(grants: list[Grant], advisor_sub: str, now: datetime) -> list[Grant]:
    return [
        g
        for g in grants
        if g.advisor_sub == advisor_sub and g.expires_at > now
    ]


def denied_fields(requested: list[Level2Field], grants: list[Grant]) -> list[Level2Field]:
    granted = {field for g in grants for field in g.fields}
    return [field for field in requested if field not in granted]
