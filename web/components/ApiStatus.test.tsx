import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiStatus } from "./ApiStatus";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("ApiStatus", () => {
  it("probes the public JWKS of copilot-api", () => {
    const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApiStatus />);
    expect(fetchMock).toHaveBeenCalledWith("http://api.test/.well-known/jwks.json", expect.anything());
    expect(screen.getByRole("status")).toHaveTextContent("Comprobando la API");
  });

  it("reports the API online with its latency", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"keys":[]}')));
    render(<ApiStatus />);
    expect(await screen.findByText(/^API en línea · \d+ ms$/)).toBeInTheDocument();
  });

  it("explains a cold start when the API takes longer than 5 s", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
    render(<ApiStatus />);
    await act(() => vi.advanceTimersByTimeAsync(4999));
    expect(screen.getByRole("status")).toHaveTextContent("Comprobando la API");
    await act(() => vi.advanceTimersByTimeAsync(1));
    expect(screen.getByRole("status")).toHaveTextContent("API iniciando (escala a cero)");
  });

  it("switches to online once a cold start finishes", async () => {
    vi.useFakeTimers();
    let respond!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise<Response>((r) => (respond = r))));
    render(<ApiStatus />);
    await act(() => vi.advanceTimersByTimeAsync(5000));
    await act(async () => respond(new Response('{"keys":[]}')));
    expect(screen.getByRole("status")).toHaveTextContent("API en línea · 5.000 ms");
  });

  it("says the API is down when the probe fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 502 })));
    render(<ApiStatus />);
    expect(await screen.findByText("API no disponible (HTTP 502)")).toBeInTheDocument();
  });

  it("says the API is unreachable when the request itself fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<ApiStatus />);
    expect(await screen.findByText("API no disponible (sin respuesta)")).toBeInTheDocument();
  });
});
