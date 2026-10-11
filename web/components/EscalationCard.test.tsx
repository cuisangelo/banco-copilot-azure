import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { decideEscalation } from "@/lib/api";
import type { EscalationDraft } from "@/lib/types";
import { EscalationCard } from "./EscalationCard";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  decideEscalation: vi.fn(),
}));

const draft: EscalationDraft = {
  id: "esc-1",
  area: "Riesgo de crédito hipotecario",
  summary: "La ficha y la circular difieren en la antigüedad laboral mínima.",
  evidence: [{ id: "d2", kind: "doc", ref: "circular-2026-07 §2", snippet: "24 meses." }],
};

beforeEach(() => vi.mocked(decideEscalation).mockReset());

describe("EscalationCard", () => {
  it("shows the drafted ticket with its evidence", () => {
    render(<EscalationCard draft={draft} token="tok-ana" onUnauthorized={vi.fn()} />);
    expect(screen.getByText(draft.area)).toBeInTheDocument();
    expect(screen.getByText(draft.summary)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /circular-2026-07 §2/ })).toBeInTheDocument();
  });

  it("creates the ticket only when the advisor approves", async () => {
    vi.mocked(decideEscalation).mockResolvedValue({ ticket_id: "ESC-4821" });
    render(<EscalationCard draft={draft} token="tok-ana" onUnauthorized={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Crear ticket" }));

    expect(decideEscalation).toHaveBeenCalledWith("esc-1", { approve: true }, "tok-ana");
    expect(screen.getByRole("status")).toHaveTextContent("Ticket ESC-4821 creado");
    expect(screen.queryByRole("button", { name: "Crear ticket" })).not.toBeInTheDocument();
  });

  it("records a discard without creating a ticket", async () => {
    vi.mocked(decideEscalation).mockResolvedValue({ discarded: true });
    render(<EscalationCard draft={draft} token={null} onUnauthorized={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "Descartar" }));

    expect(decideEscalation).toHaveBeenCalledWith("esc-1", { approve: false }, null);
    expect(screen.getByRole("status")).toHaveTextContent("Escalamiento descartado");
  });
});
