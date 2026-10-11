import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, sendFeedback } from "@/lib/api";
import { AnswerFeedback } from "./AnswerFeedback";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  sendFeedback: vi.fn(),
}));

const onUnauthorized = vi.fn();

function renderFeedback(token: string | null = "tok-ana") {
  render(
    <AnswerFeedback sessionId="s-1" turnIndex={3} answerStatus="insufficient" token={token} onUnauthorized={onUnauthorized} />,
  );
}

beforeEach(() => {
  vi.mocked(sendFeedback).mockReset().mockResolvedValue({ id: "feedback:ana:s-1:3" });
  onUnauthorized.mockReset();
});

describe("AnswerFeedback", () => {
  it("sends a thumbs up right away and disables both buttons", async () => {
    renderFeedback();
    await userEvent.click(screen.getByRole("button", { name: "Respuesta útil" }));

    expect(sendFeedback).toHaveBeenCalledWith(
      { session_id: "s-1", turn_index: 3, rating: "up", comment: null, answer_status: "insufficient" },
      "tok-ana",
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Gracias por calificar");
    expect(screen.getByRole("button", { name: "Respuesta útil" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Respuesta no útil" })).toBeDisabled();
  });

  it("opens an optional comment for a thumbs down and sends it", async () => {
    renderFeedback(null);
    await userEvent.click(screen.getByRole("button", { name: "Respuesta no útil" }));
    expect(sendFeedback).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText(/Qué faltó/), "No citó el procedimiento");
    await userEvent.click(screen.getByRole("button", { name: "Enviar calificación" }));

    expect(sendFeedback).toHaveBeenCalledWith(
      { session_id: "s-1", turn_index: 3, rating: "down", comment: "No citó el procedimiento", answer_status: "insufficient" },
      null,
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Gracias por calificar");
  });

  it("sends a thumbs down without a comment as null", async () => {
    renderFeedback();
    await userEvent.click(screen.getByRole("button", { name: "Respuesta no útil" }));
    await userEvent.click(screen.getByRole("button", { name: "Enviar calificación" }));

    expect(vi.mocked(sendFeedback).mock.calls[0][0].comment).toBeNull();
  });

  it("shows a 409 as already rated", async () => {
    vi.mocked(sendFeedback).mockRejectedValue(new ApiError(409));
    renderFeedback();
    await userEvent.click(screen.getByRole("button", { name: "Respuesta útil" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Ya calificaste esta respuesta");
    expect(screen.getByRole("button", { name: "Respuesta útil" })).toBeDisabled();
  });

  it("lets the advisor retry after another failure", async () => {
    vi.mocked(sendFeedback).mockRejectedValueOnce(new ApiError(429));
    renderFeedback();
    await userEvent.click(screen.getByRole("button", { name: "Respuesta útil" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiadas acciones seguidas");
    await userEvent.click(screen.getByRole("button", { name: "Respuesta útil" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Gracias por calificar");
  });

  it("hands a 401 to the session", async () => {
    vi.mocked(sendFeedback).mockRejectedValue(new ApiError(401));
    renderFeedback();
    await userEvent.click(screen.getByRole("button", { name: "Respuesta útil" }));

    expect(onUnauthorized).toHaveBeenCalled();
  });
});
