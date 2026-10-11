import json
import time
from collections.abc import Callable, Iterable

import httpx


def parse_sse(lines: Iterable[str]) -> tuple[dict | None, list[dict], dict | None]:
    """Split a copilot-api SSE stream into (answer, trace events, error)."""
    answer, error, traces = None, None, []
    event = None
    for line in lines:
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            payload = json.loads(line[5:].strip())
            if event == "trace":
                traces.append(payload)
            elif event == "answer":
                answer = payload
            elif event == "error":
                error = payload
    return answer, traces, error


# copilot-api allows 10 requests per minute per IP; the runner stays under it instead of bypassing it.
# Every call is spaced, so the runner holds whichever routes the limiter counts.
MIN_SECONDS_BETWEEN_CALLS = 6.5


class CopilotClient:
    def __init__(self, http: httpx.Client, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self._http = http
        self._clock = clock
        self._sleep = sleep
        self._last_call = -MIN_SECONDS_BETWEEN_CALLS

    def token(self, persona: str) -> str:
        self._wait_turn()
        response = self._http.post("/demo/session", json={"persona": persona})
        response.raise_for_status()
        return response.json()["token"]

    def chat(self, token: str | None, session_id: str, message: str, customer_id: str | None):
        body = {"session_id": session_id, "message": message, "customer_id": customer_id}
        return self._stream("/chat", token, body)

    def resume(self, token: str, session_id: str):
        return self._stream(f"/sessions/{session_id}/resume", token, None)

    def decide_access(self, supervisor_token: str, request_id: str, fields: list[str]) -> dict:
        self._wait_turn()
        response = self._http.post(
            f"/access-requests/{request_id}/decision",
            json={"approved_fields": fields},
            headers={"Authorization": f"Bearer {supervisor_token}"},
        )
        response.raise_for_status()
        return response.json()

    def _wait_turn(self) -> None:
        self._sleep(max(0.0, self._last_call + MIN_SECONDS_BETWEEN_CALLS - self._clock()))
        self._last_call = self._clock()

    def _stream(self, path: str, token: str | None, body: dict | None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        self._wait_turn()
        started = time.perf_counter()
        with self._http.stream("POST", path, json=body, headers=headers) as response:
            response.raise_for_status()
            answer, traces, error = parse_sse(response.iter_lines())
        latency_ms = int((time.perf_counter() - started) * 1000)
        return answer, traces, error, latency_ms
