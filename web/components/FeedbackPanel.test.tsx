import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createDemoSession, listFeedback } from "@/lib/api";
import { SessionProvider } from "@/lib/session";
import type { Feedback } from "@/lib/types";
import { FeedbackPanel } from "./FeedbackPanel";
import { PersonaPicker } from "./PersonaPicker";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  createDemoSession: vi.fn(),
  listFeedback: vi.fn(),
}));

const rated = (overrides: Partial<Feedback>): Feedback => ({
  id: "feedback:ana:s-1:0",
  actor: "ana",
  created_at: "2026-10-11T23:00:00Z",
  session_id: "s-1",
  turn_index: 0,
  rating: "up",
  comment: null,
  answer_status: "ok",
  ...overrides,
});

const feedback: Feedback[] = [
  rated({ id: "f-3", actor: "anonymous", rating: "up" }),
  rated({ id: "f-2", actor: "bruno", rating: "down", comment: "No citó la circular", answer_status: "contradiction" }),
  rated({ id: "f-1", actor: "ana", rating: "up" }),
];

async function renderAs(persona: "sofia" | "ana") {
  vi.mocked(createDemoSession).mockResolvedValue(
    persona === "sofia" ? { token: "tok-sofia", name: "Sofía", role: "Supervisor" } : { token: "tok-ana", name: "Ana", role: "Asesor" },
  );
  render(
    <SessionProvider>
      <PersonaPicker />
      <FeedbackPanel />
    </SessionProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /persona/i }));
  await userEvent.click(screen.getByRole("option", { name: persona === "sofia" ? /Sofía/ : /Ana/ }));
}

beforeEach(() => {
  vi.mocked(listFeedback).mockReset().mockResolvedValue(feedback);
});

describe("FeedbackPanel", () => {
  it("asks for the Supervisor persona instead of loading for an Asesor", async () => {
    await renderAs("ana");

    expect(screen.getByText(/Elige a Sofía/)).toBeInTheDocument();
    expect(listFeedback).not.toHaveBeenCalled();
  });

  it("shows the share of thumbs up and one row per rating", async () => {
    await renderAs("sofia");

    const table = await screen.findByRole("table", { name: "Calificaciones del copiloto" });
    expect(listFeedback).toHaveBeenCalledWith("tok-sofia");
    expect(screen.getByText(/67\s?%/)).toBeInTheDocument();
    const [, anonymous, bruno] = within(table).getAllByRole("row");
    expect(anonymous).toHaveTextContent("Anónimo");
    expect(bruno).toHaveTextContent("Bruno");
    expect(bruno).toHaveTextContent("Fuentes en conflicto");
    expect(bruno).toHaveTextContent("No útil");
    expect(bruno).toHaveTextContent("No citó la circular");
  });

  it("says so when nobody rated yet", async () => {
    vi.mocked(listFeedback).mockResolvedValue([]);
    await renderAs("sofia");

    expect(await screen.findByText(/Aún no hay calificaciones/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("reports a failed load", async () => {
    vi.mocked(listFeedback).mockRejectedValue(new ApiError(500));
    await renderAs("sofia");

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo cargar el feedback");
  });
});
