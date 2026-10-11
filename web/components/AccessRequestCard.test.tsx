import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getAccessRequest } from "@/lib/api";
import type { AccessRequest } from "@/lib/types";
import { AccessRequestCard, POLL_MS } from "./AccessRequestCard";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getAccessRequest: vi.fn(),
}));

const pending: AccessRequest = {
  id: "ar-1",
  customer_id: "C-1042",
  fields: ["monthly_income", "employment_tenure_months"],
  purpose: "Verificar renta y antigüedad para el hipotecario.",
  requested_by: "ana",
  status: "pending",
  created_at: "2026-10-11T15:00:00Z",
  decided_by: null,
  decided_at: null,
  approved_fields: [],
};

const partial: AccessRequest = {
  ...pending,
  status: "partially_approved",
  decided_by: "sofia",
  decided_at: "2026-10-11T15:02:00Z",
  approved_fields: ["monthly_income"],
};

function renderCard(onDecided = vi.fn(), onUnauthorized = vi.fn()) {
  render(<AccessRequestCard request={pending} token="tok-ana" onDecided={onDecided} onUnauthorized={onUnauthorized} />);
  return { onDecided, onUnauthorized };
}

const tick = () => act(() => vi.advanceTimersByTimeAsync(POLL_MS));

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("AccessRequestCard", () => {
  it("shows what was requested and that it awaits a Supervisor", () => {
    renderCard();
    expect(screen.getByText("C-1042")).toBeInTheDocument();
    expect(screen.getByText("Renta mensual")).toBeInTheDocument();
    expect(screen.getByText("Antigüedad laboral")).toBeInTheDocument();
    expect(screen.getByText(pending.purpose)).toBeInTheDocument();
    expect(screen.getByText("Esperando al Supervisor")).toBeInTheDocument();
  });

  it("polls with the advisor token until the request is decided, then reports it once", async () => {
    vi.mocked(getAccessRequest).mockResolvedValueOnce(pending).mockResolvedValue(partial);
    const { onDecided } = renderCard();

    await tick();
    expect(onDecided).not.toHaveBeenCalled();
    await tick();
    await tick();

    expect(getAccessRequest).toHaveBeenCalledWith("ar-1", "tok-ana");
    expect(getAccessRequest).toHaveBeenCalledTimes(2);
    expect(onDecided).toHaveBeenCalledExactlyOnceWith(partial);
    expect(screen.getByText("Aprobada en parte")).toBeInTheDocument();
    expect(screen.getByText("Antigüedad laboral").closest("li")).toHaveTextContent("No autorizado");
  });

  it("hands a 401 to the session instead of polling forever", async () => {
    vi.mocked(getAccessRequest).mockRejectedValue(new ApiError(401));
    const { onUnauthorized } = renderCard();

    await tick();
    await tick();

    expect(onUnauthorized).toHaveBeenCalledOnce();
    expect(getAccessRequest).toHaveBeenCalledOnce();
  });
});
