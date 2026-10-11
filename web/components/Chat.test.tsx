import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createDemoSession, resumeSession, sendFeedback, streamChat } from "@/lib/api";
import type { ChatEvent } from "@/lib/api";
import { SessionProvider } from "@/lib/session";
import type { AccessRequest, ChatAnswer } from "@/lib/types";
import { Chat } from "./Chat";
import { PersonaPicker } from "./PersonaPicker";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  createDemoSession: vi.fn(),
  streamChat: vi.fn(),
  resumeSession: vi.fn(),
  sendFeedback: vi.fn(),
}));

// The card's own polling is covered in AccessRequestCard.test; here only the hand-off to resume matters.
vi.mock("./AccessRequestCard", () => ({
  AccessRequestCard: ({ request, onDecided }: { request: AccessRequest; onDecided: (r: AccessRequest) => void }) => (
    <button onClick={() => onDecided({ ...request, status: "approved", approved_fields: request.fields })}>
      simular aprobación
    </button>
  ),
}));

function answer(overrides: Partial<ChatAnswer>): ChatAnswer {
  return {
    status: "ok",
    message: "Respuesta",
    requirements: [],
    steps: [],
    citations: [],
    access_request: null,
    escalation: null,
    ...overrides,
  };
}

async function* events(...items: ChatEvent[]) {
  for (const item of items) yield item;
}

async function* failing(status: number): AsyncGenerator<ChatEvent> {
  throw new ApiError(status);
}

const accessRequest: AccessRequest = {
  id: "ar-1",
  customer_id: "C-1042",
  fields: ["monthly_income"],
  purpose: "Verificar renta para el hipotecario.",
  requested_by: "ana",
  status: "pending",
  created_at: "2026-10-11T15:00:00Z",
  decided_by: null,
  decided_at: null,
  approved_fields: [],
};

function renderChat() {
  render(
    <SessionProvider>
      <PersonaPicker />
      <Chat />
    </SessionProvider>,
  );
}

async function signInAsAna() {
  await userEvent.click(screen.getByRole("button", { name: /persona/i }));
  await userEvent.click(screen.getByRole("option", { name: /Ana/ }));
}

async function ask(text: string) {
  await userEvent.type(screen.getByLabelText("Consulta"), text);
  await userEvent.click(screen.getByRole("button", { name: "Consultar" }));
}

beforeEach(() => {
  vi.mocked(streamChat).mockReset();
  vi.mocked(resumeSession).mockReset();
  vi.mocked(createDemoSession).mockResolvedValue({ token: "tok-ana", name: "Ana", role: "Asesor" });
});

describe("Chat", () => {
  it("rejects a malformed customer id before sending", async () => {
    renderChat();
    await userEvent.type(screen.getByLabelText("Cliente en atención"), "1042");
    await userEvent.type(screen.getByLabelText("Consulta"), "¿Qué le ofrezco?");

    expect(screen.getByText("Usa el formato C-1234")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Consultar" })).toBeDisabled();
  });

  it("sends the question with session, customer and token, and renders the streamed answer", async () => {
    vi.mocked(streamChat).mockReturnValue(
      events(
        { type: "trace", payload: { node: "router", duration_ms: 5, data: {}, tokens_in: 1, tokens_out: 1, cost_usd: 0 } },
        { type: "answer", payload: answer({ message: "Pide la cédula." }) },
      ),
    );
    renderChat();
    await signInAsAna();
    await userEvent.type(screen.getByLabelText("Cliente en atención"), "C-1042");
    await ask("¿Qué le pido?");

    const [body, token] = vi.mocked(streamChat).mock.calls[0];
    expect(body).toEqual({ session_id: expect.any(String), message: "¿Qué le pido?", customer_id: "C-1042" });
    expect(token).toBe("tok-ana");
    expect(await screen.findByText("Pide la cédula.")).toBeInTheDocument();
    expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
  });

  it("sends anonymously at level 0 without a persona", async () => {
    vi.mocked(streamChat).mockReturnValue(events({ type: "answer", payload: answer({}) }));
    renderChat();
    await ask("¿Tasa de la tarjeta Oro?");

    expect(vi.mocked(streamChat).mock.calls[0]).toEqual([
      { session_id: expect.any(String), message: "¿Tasa de la tarjeta Oro?", customer_id: null },
      null,
    ]);
  });

  it("shows an error event in place of an answer", async () => {
    vi.mocked(streamChat).mockReturnValue(
      events({ type: "error", payload: { code: "token_cap", message: "Se alcanzó el tope diario." } }),
    );
    renderChat();
    await ask("hola");

    expect(await screen.findByRole("alert")).toHaveTextContent("Se alcanzó el tope diario.");
  });

  it("sends the advisor back to the persona picker on 401", async () => {
    vi.mocked(streamChat).mockReturnValue(failing(401));
    renderChat();
    await signInAsAna();
    await ask("hola");

    expect(await screen.findByText(/sesión de demo venció/)).toBeInTheDocument();
  });

  it("resumes the session once the access request is decided", async () => {
    vi.mocked(streamChat).mockReturnValue(
      events({ type: "answer", payload: answer({ status: "access_required", access_request: accessRequest }) }),
    );
    vi.mocked(resumeSession).mockReturnValue(events({ type: "answer", payload: answer({ message: "Renta verificada." }) }));
    renderChat();
    await signInAsAna();
    await ask("¿C-1042 cumple?");

    await userEvent.click(await screen.findByRole("button", { name: "simular aprobación" }));

    const sessionId = vi.mocked(streamChat).mock.calls[0][0].session_id;
    expect(resumeSession).toHaveBeenCalledWith(sessionId, "tok-ana");
    expect(await screen.findByText("Renta verificada.")).toBeInTheDocument();
  });

  it("tells the advisor when there is nothing to resume", async () => {
    vi.mocked(streamChat).mockReturnValue(
      events({ type: "answer", payload: answer({ status: "access_required", access_request: accessRequest }) }),
    );
    vi.mocked(resumeSession).mockReturnValue(failing(409));
    renderChat();
    await signInAsAna();
    await ask("¿C-1042 cumple?");

    await userEvent.click(await screen.findByRole("button", { name: "simular aprobación" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No hay nada que reanudar");
  });

  it("rates each answer by its position in the session", async () => {
    vi.mocked(sendFeedback).mockResolvedValue({ id: "f-1" });
    vi.mocked(streamChat)
      .mockReturnValueOnce(events({ type: "answer", payload: answer({ message: "Primera." }) }))
      .mockReturnValueOnce(events({ type: "answer", payload: answer({ status: "insufficient", message: "Segunda." }) }));
    renderChat();
    await signInAsAna();
    await ask("uno");
    await screen.findByText("Primera.");
    await ask("dos");
    await screen.findByText("Segunda.");

    const [, second] = screen.getAllByRole("button", { name: "Respuesta útil" });
    await userEvent.click(second);

    const sessionId = vi.mocked(streamChat).mock.calls[0][0].session_id;
    expect(sendFeedback).toHaveBeenCalledWith(
      { session_id: sessionId, turn_index: 1, rating: "up", comment: null, answer_status: "insufficient" },
      "tok-ana",
    );
  });
});
