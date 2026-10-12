import json

import httpx

from evals.client import MIN_SECONDS_BETWEEN_CALLS, CopilotClient
from evals.run import run_row


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def sse(event, payload):
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


def copilot_api(clock, started):
    def handle(request):
        started.append((request.url.path, clock.now))
        clock.now += 0.2
        if request.url.path == "/demo/session":
            return httpx.Response(200, json={"token": "tok"})
        if request.url.path.endswith("/decision"):
            return httpx.Response(200, json={"id": "ar-1", "status": "approved"})
        if request.url.path == "/chat":
            answer = {"status": "access_required", "access_request": {"id": "ar-1"}}
        else:
            answer = {"status": "ok", "citations": []}
        return httpx.Response(200, text=sse("answer", answer), headers={"content-type": "text/event-stream"})

    return handle


def test_runner_spaces_every_api_call_not_only_streams():
    clock, started = FakeClock(), []
    http = httpx.Client(base_url="http://copilot", transport=httpx.MockTransport(copilot_api(clock, started)))
    client = CopilotClient(http, clock=clock.monotonic, sleep=clock.sleep)
    row = {"type": "cliente_nivel2_con_permiso", "persona": "ana", "question": "q", "customer_id": "C-1007",
           "grant_fields": ["monthly_income"]}

    answer, _, _, _ = run_row(client, row)

    assert answer["status"] == "ok"
    paths = [path for path, _ in started]
    assert paths[:4] == ["/demo/session", "/chat", "/demo/session", "/access-requests/ar-1/decision"]
    assert paths[4].startswith("/sessions/") and paths[4].endswith("/resume")
    gaps = [later - earlier for (_, earlier), (_, later) in zip(started, started[1:])]
    assert all(gap >= MIN_SECONDS_BETWEEN_CALLS for gap in gaps), gaps


def test_chat_asks_for_the_runner_retrieval_mode():
    bodies = []

    def handle(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, text=sse("answer", {"status": "ok"}), headers={"content-type": "text/event-stream"})

    clock = FakeClock()
    http = httpx.Client(base_url="http://copilot", transport=httpx.MockTransport(handle))
    client = CopilotClient(http, retrieval_mode="agentic", clock=clock.monotonic, sleep=clock.sleep)

    client.chat(None, "s-1", "¿Diferencia entre Oro y Platinum?", None)

    assert bodies[0]["retrieval_mode"] == "agentic"
