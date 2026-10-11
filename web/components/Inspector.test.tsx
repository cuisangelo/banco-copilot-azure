import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TraceEvent } from "@/lib/types";
import { Inspector } from "./Inspector";

const traces: TraceEvent[] = [
  { node: "router", duration_ms: 410, data: { route: "procedure" }, tokens_in: 612, tokens_out: 9, cost_usd: 0.000259 },
  { node: "rag_agent", duration_ms: 820, data: { chunks: [] }, tokens_in: 96, tokens_out: 0, cost_usd: 0.000038 },
];

describe("Inspector", () => {
  it("lists each node with duration, tokens and cost", () => {
    render(<Inspector turns={[{ id: "t1", title: "¿Qué le pido?", traces }]} />);
    const row = screen.getByText("Clasificación").closest("li")!;
    expect(row).toHaveTextContent("router");
    expect(row).toHaveTextContent("410 ms");
    expect(row).toHaveTextContent("612 entrada");
    expect(row).toHaveTextContent("9 salida");
    expect(row).toHaveTextContent("US$0,000259");
  });

  it("totals the turn", () => {
    render(<Inspector turns={[{ id: "t1", title: "¿Qué le pido?", traces }]} />);
    const totals = screen.getByLabelText("Totales del turno");
    expect(totals).toHaveTextContent("1.230 ms");
    expect(totals).toHaveTextContent("717 tokens");
    expect(totals).toHaveTextContent("US$0,000297");
  });

  it("shows the newest turn first", () => {
    render(
      <Inspector
        turns={[
          { id: "t1", title: "Primera", traces },
          { id: "t2", title: "Segunda", traces },
        ]}
      />,
    );
    const titles = within(screen.getByRole("list", { name: "Turnos" }))
      .getAllByRole("heading")
      .map((h) => h.textContent);
    expect(titles).toEqual(["Segunda", "Primera"]);
  });

  it("invites a first question when there is nothing to inspect", () => {
    render(<Inspector turns={[]} />);
    expect(screen.getByText(/Haz una consulta/)).toBeInTheDocument();
  });
});
