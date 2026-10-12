import { parseSSE } from "./sse";
import type {
  AccessDecision,
  AccessRequest,
  AccessRequestStatus,
  ChatAnswer,
  ChatRequest,
  DemoSession,
  ErrorEvent,
  EscalationDecision,
  Feedback,
  FeedbackCreate,
  PersonaKey,
  RetrievalMode,
  TraceEvent,
} from "./types";

// Guaranteed at build time by next.config.ts.
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL;

export class ApiError extends Error {
  constructor(readonly status: number) {
    super(`copilot-api responded ${status}`);
  }
}

export type ChatEvent =
  | { type: "trace"; payload: TraceEvent }
  | { type: "answer"; payload: ChatAnswer }
  | { type: "error"; payload: ErrorEvent };

function auth(token: string | null): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) throw new ApiError(response.status);
  return response;
}

async function* events(response: Response): AsyncGenerator<ChatEvent> {
  for await (const { event, data } of parseSSE(response.body!)) {
    if (event !== "trace" && event !== "answer" && event !== "error") {
      throw new Error(`Unexpected SSE event "${event}" from copilot-api`);
    }
    yield { type: event, payload: JSON.parse(data) } as ChatEvent;
  }
}

export async function* streamChat(body: ChatRequest, token: string | null): AsyncGenerator<ChatEvent> {
  const response = await request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth(token) },
    body: JSON.stringify(body),
  });
  yield* events(response);
}

export async function* resumeSession(sessionId: string, token: string): AsyncGenerator<ChatEvent> {
  const response = await request(`/sessions/${sessionId}/resume`, { method: "POST", headers: auth(token) });
  yield* events(response);
}

async function postJson<T>(path: string, body: unknown, token: string | null): Promise<T> {
  const response = await request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...auth(token) },
    body: JSON.stringify(body),
  });
  return response.json();
}

export async function getRetrievalModes(): Promise<RetrievalMode[]> {
  return (await (await request("/status", {})).json()).retrieval_modes;
}

export function createDemoSession(persona: PersonaKey): Promise<DemoSession> {
  return postJson("/demo/session", { persona }, null);
}

export async function getAccessRequest(id: string, token: string): Promise<AccessRequest> {
  return (await request(`/access-requests/${id}`, { headers: auth(token) })).json();
}

export async function listAccessRequests(token: string, status?: AccessRequestStatus): Promise<AccessRequest[]> {
  const query = status ? `?status=${status}` : "";
  return (await request(`/access-requests${query}`, { headers: auth(token) })).json();
}

export function decideAccessRequest(id: string, decision: AccessDecision, token: string): Promise<AccessRequest> {
  return postJson(`/access-requests/${id}/decision`, decision, token);
}

export function decideEscalation(
  id: string,
  decision: EscalationDecision,
  token: string | null,
): Promise<{ ticket_id: string } | { discarded: true }> {
  return postJson(`/escalations/${id}/decision`, decision, token);
}

export function sendFeedback(feedback: FeedbackCreate, token: string | null): Promise<{ id: string }> {
  return postJson("/feedback", feedback, token);
}

export async function listFeedback(token: string): Promise<Feedback[]> {
  return (await request("/feedback?limit=50", { headers: auth(token) })).json();
}
