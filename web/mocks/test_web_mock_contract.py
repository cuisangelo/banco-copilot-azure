"""The web mock must speak exactly the copilot-api contract: every payload round-trips through bank_contracts."""

import json
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest
from pydantic import BaseModel, TypeAdapter

from bank_contracts.auth import PERSONAS
from bank_contracts.models import AccessRequest, ChatAnswer, ErrorEvent, TraceEvent

SERVER = Path(__file__).with_name("server.mjs")
SSE_MODELS: dict[str, type[BaseModel]] = {"trace": TraceEvent, "answer": ChatAnswer, "error": ErrorEvent}


def assert_exact(model: type[BaseModel], payload: dict) -> BaseModel:
    parsed = model.model_validate(payload)
    assert parsed.model_dump(mode="json") == payload
    return parsed


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(["node", str(SERVER), str(port)])
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.1)
    yield url
    proc.terminate()
    proc.wait()


def call(base_url: str, method: str, path: str, body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"} if body is not None else {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base_url + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()


def sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def stream(base_url: str, path: str, body: dict | None, token: str | None) -> list[tuple[str, BaseModel]]:
    status, text = call(base_url, "POST", path, body, token)
    assert status == 200, text
    events = [(name, assert_exact(SSE_MODELS[name], payload)) for name, payload in sse(text)]
    assert [name for name, _ in events[:-1]] == ["trace"] * (len(events) - 1)
    assert events[-1][0] in ("answer", "error")
    return events


def login(base_url: str, persona: str) -> str:
    status, text = call(base_url, "POST", "/demo/session", {"persona": persona})
    assert status == 200
    session = json.loads(text)
    name, role = PERSONAS[persona]
    assert session == {"token": session["token"], "name": name, "role": role}
    return session["token"]


MESSAGES = [
    ("Cliente dependiente quiere abrir cuenta sueldo, ¿qué le pido?", None, "ok"),
    ("¿Diferencia entre Oro y Platinum?", None, "ok"),
    ("Cliente quiere un crédito de consumo", None, "clarification"),
    ("¿Antigüedad laboral mínima para el hipotecario?", None, "contradiction"),
    ("¿Qué opinas de bitcoin?", None, "rejected"),
    ("¿Requisito para abrir una cuenta en dólares?", None, "insufficient"),
    ("Atiendo al cliente, ¿qué le puedo ofrecer?", "C-1042", "ok"),
]


@pytest.mark.parametrize(("message", "customer_id", "status"), MESSAGES)
def test_chat_scenarios_emit_contract_events(base_url, message, customer_id, status):
    token = login(base_url, "ana")
    events = stream(base_url, "/chat", {"session_id": f"s-{status}", "message": message, "customer_id": customer_id}, token)
    assert events[-1][1].status == status


def test_error_event_replaces_answer(base_url):
    events = stream(base_url, "/chat", {"session_id": "s-cap", "message": "simular tope", "customer_id": None}, None)
    assert events[-1][0] == "error"


def test_access_request_round_trip(base_url):
    ana, sofia = login(base_url, "ana"), login(base_url, "sofia")
    session = "s-access"
    events = stream(
        base_url, "/chat", {"session_id": session, "message": "¿C-1042 cumple para el hipotecario?", "customer_id": "C-1042"}, ana
    )
    answer = events[-1][1]
    assert answer.status == "access_required"
    request_id = answer.access_request.id

    status, text = call(base_url, "GET", f"/access-requests/{request_id}", token=ana)
    assert status == 200 and assert_exact(AccessRequest, json.loads(text)).status == "pending"

    status, text = call(base_url, "GET", "/access-requests?status=pending", token=sofia)
    pending = TypeAdapter(list[AccessRequest]).validate_python(json.loads(text))
    assert request_id in [r.id for r in pending]

    assert call(base_url, "POST", f"/sessions/{session}/resume", token=ana)[0] == 409
    decision = {"approved_fields": [answer.access_request.fields[0]]}
    assert call(base_url, "POST", f"/access-requests/{request_id}/decision", decision, ana)[0] == 403
    status, text = call(base_url, "POST", f"/access-requests/{request_id}/decision", decision, sofia)
    assert status == 200 and assert_exact(AccessRequest, json.loads(text)).status == "partially_approved"
    assert call(base_url, "POST", f"/access-requests/{request_id}/decision", decision, sofia)[0] == 409

    resumed = stream(base_url, f"/sessions/{session}/resume", None, ana)
    assert resumed[-1][1].status == "ok"
    assert call(base_url, "POST", f"/sessions/{session}/resume", token=ana)[0] == 409


def test_escalation_decision(base_url):
    events = stream(
        base_url, "/chat", {"session_id": "s-esc", "message": "¿Antigüedad laboral mínima para el hipotecario?", "customer_id": None}, None
    )
    escalation = events[-1][1].escalation
    status, text = call(base_url, "POST", f"/escalations/{escalation.id}/decision", {"approve": True})
    assert status == 200 and set(json.loads(text)) == {"ticket_id"}


def test_unknown_token_is_401(base_url):
    assert call(base_url, "POST", "/chat", {"session_id": "s", "message": "hola", "customer_id": None}, "expired")[0] == 401
