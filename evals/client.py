import json
import time
from collections.abc import Iterable

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


class CopilotClient:
    def __init__(self, base_url: str):
        self._http = httpx.Client(base_url=base_url, timeout=120)

    def token(self, persona: str) -> str:
        response = self._http.post("/demo/session", json={"persona": persona})
        response.raise_for_status()
        return response.json()["token"]

    def chat(self, token: str | None, session_id: str, message: str, customer_id: str | None):
        body = {"session_id": session_id, "message": message, "customer_id": customer_id}
        return self._stream("/chat", token, body)

    def resume(self, token: str, session_id: str):
        return self._stream(f"/sessions/{session_id}/resume", token, None)

    def decide_access(self, supervisor_token: str, request_id: str, fields: list[str]) -> dict:
        response = self._http.post(
            f"/access-requests/{request_id}/decision",
            json={"approved_fields": fields},
            headers={"Authorization": f"Bearer {supervisor_token}"},
        )
        response.raise_for_status()
        return response.json()

    def _stream(self, path: str, token: str | None, body: dict | None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        started = time.perf_counter()
        with self._http.stream("POST", path, json=body, headers=headers) as response:
            response.raise_for_status()
            answer, traces, error = parse_sse(response.iter_lines())
        latency_ms = int((time.perf_counter() - started) * 1000)
        return answer, traces, error, latency_ms
