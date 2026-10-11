import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  createDemoSession,
  decideAccessRequest,
  listFeedback,
  resumeSession,
  sendFeedback,
  streamChat,
} from "./api";
import type { ChatEvent } from "./api";

function sseResponse(body: string, status = 200): Response {
  return new Response(body, { status, headers: { "Content-Type": "text/event-stream" } });
}

async function collect(events: AsyncGenerator<ChatEvent>) {
  const out = [];
  for await (const event of events) out.push(event);
  return out;
}

const answer = {
  status: "ok",
  message: "Listo",
  requirements: [],
  steps: [],
  citations: [],
  access_request: null,
  escalation: null,
};

afterEach(() => vi.unstubAllGlobals());

describe("streamChat", () => {
  it("posts the request with the persona token and yields typed events", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse(
        `event: trace\ndata: {"node":"router","duration_ms":12,"data":{},"tokens_in":5,"tokens_out":1,"cost_usd":0.0001}\n\n` +
          `event: answer\ndata: ${JSON.stringify(answer)}\n\n`,
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const events = await collect(
      streamChat({ session_id: "s1", message: "hola", customer_id: null }, "tok-ana"),
    );

    expect(fetchMock).toHaveBeenCalledWith("http://api.test/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer tok-ana" },
      body: JSON.stringify({ session_id: "s1", message: "hola", customer_id: null }),
    });
    expect(events.map((e) => e.type)).toEqual(["trace", "answer"]);
    expect(events[1]).toEqual({ type: "answer", payload: answer });
  });

  it("omits Authorization when there is no persona", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(`event: answer\ndata: ${JSON.stringify(answer)}\n\n`));
    vi.stubGlobal("fetch", fetchMock);

    await collect(streamChat({ session_id: "s1", message: "hola", customer_id: null }, null));

    expect(fetchMock.mock.calls[0][1].headers).toEqual({ "Content-Type": "application/json" });
  });

  it("throws ApiError with the HTTP status when the request is rejected", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 401 })));

    await expect(collect(streamChat({ session_id: "s1", message: "x", customer_id: null }, "old"))).rejects.toEqual(
      new ApiError(401),
    );
  });

  it("fails loudly on an event name outside the contract", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(sseResponse("event: surprise\ndata: {}\n\n")));

    await expect(collect(streamChat({ session_id: "s1", message: "x", customer_id: null }, null))).rejects.toThrow(
      "surprise",
    );
  });
});

describe("resumeSession", () => {
  it("posts without a body to the session resume route", async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse(`event: answer\ndata: ${JSON.stringify(answer)}\n\n`));
    vi.stubGlobal("fetch", fetchMock);

    await collect(resumeSession("s1", "tok-ana"));

    expect(fetchMock).toHaveBeenCalledWith("http://api.test/sessions/s1/resume", {
      method: "POST",
      headers: { Authorization: "Bearer tok-ana" },
    });
  });

  it("surfaces 409 when there is nothing to resume", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 409 })));

    await expect(collect(resumeSession("s1", "tok-ana"))).rejects.toEqual(new ApiError(409));
  });
});

describe("JSON endpoints", () => {
  it("creates a demo session for a persona", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(Response.json({ token: "t", name: "Ana", role: "Asesor" }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(createDemoSession("ana")).resolves.toEqual({ token: "t", name: "Ana", role: "Asesor" });
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/demo/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ persona: "ana" }),
    });
  });

  it("surfaces 409 when an access request was already decided", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 409 })));

    await expect(decideAccessRequest("ar-1", { approved_fields: [] }, "tok-sofia")).rejects.toEqual(
      new ApiError(409),
    );
  });
});

describe("feedback", () => {
  const rating = { session_id: "s1", turn_index: 2, rating: "down", comment: "Faltó la fuente", answer_status: "ok" } as const;

  it("posts the rating with the persona token and returns its id", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ id: "feedback:ana:s1:2" }, { status: 201 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(sendFeedback(rating, "tok-ana")).resolves.toEqual({ id: "feedback:ana:s1:2" });
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer tok-ana" },
      body: JSON.stringify(rating),
    });
  });

  it("surfaces 409 when the turn was already rated", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("{}", { status: 409 })));

    await expect(sendFeedback(rating, null)).rejects.toEqual(new ApiError(409));
  });

  it("lists the latest feedback for a Supervisor", async () => {
    const fetchMock = vi.fn().mockResolvedValue(Response.json([]));
    vi.stubGlobal("fetch", fetchMock);

    await expect(listFeedback("tok-sofia")).resolves.toEqual([]);
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/feedback?limit=50", {
      headers: { Authorization: "Bearer tok-sofia" },
    });
  });
});
