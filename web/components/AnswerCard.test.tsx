import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ChatAnswer } from "@/lib/types";
import { AnswerCard } from "./AnswerCard";

const answer: ChatAnswer = {
  status: "ok",
  message: "Pide estos documentos.",
  requirements: [
    { text: "Cédula de identidad vigente", citation_ids: ["c1"] },
    { text: "Tres últimas liquidaciones", citation_ids: ["c1"] },
  ],
  steps: [
    { text: "Valida la identidad", citation_ids: ["c2"] },
    { text: "Firma el contrato", citation_ids: ["c2"] },
  ],
  citations: [
    { id: "c1", kind: "doc", ref: "ficha-cuenta-sueldo §Requisitos", snippet: "Cédula vigente y tres liquidaciones." },
    { id: "c2", kind: "doc", ref: "procedimiento-apertura §Validación", snippet: "Validar con huella." },
  ],
  access_request: null,
  escalation: null,
};

describe("AnswerCard", () => {
  it.each([
    ["ok", "Respuesta con fuentes"],
    ["clarification", "Falta un dato"],
    ["insufficient", "Sin respaldo suficiente"],
    ["contradiction", "Fuentes en conflicto"],
    ["rejected", "Consulta rechazada"],
    ["access_required", "Requiere acceso a datos"],
  ] as const)("labels status %s in Spanish", (status, label) => {
    render(<AnswerCard answer={{ ...answer, status }} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("renders requirements as a checklist the advisor can tick", async () => {
    render(<AnswerCard answer={answer} />);
    const item = screen.getByRole("checkbox", { name: /Cédula de identidad vigente/ });
    expect(item).not.toBeChecked();
    await userEvent.click(item);
    expect(item).toBeChecked();
  });

  it("renders steps as a numbered list", () => {
    render(<AnswerCard answer={answer} />);
    const steps = screen.getByRole("list", { name: "Pasos" });
    expect(steps.tagName).toBe("OL");
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      expect.stringContaining("Valida la identidad"),
      expect.stringContaining("Firma el contrato"),
    ]);
  });

  it("opens the cited snippet from a citation chip", async () => {
    render(<AnswerCard answer={answer} />);
    const [chip] = screen.getAllByRole("button", { name: /procedimiento-apertura §Validación/ });
    expect(screen.queryByText("Validar con huella.")).not.toBeInTheDocument();

    await userEvent.click(chip);

    expect(chip).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Validar con huella.")).toBeVisible();
  });
});
