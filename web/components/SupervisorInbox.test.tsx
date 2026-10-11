import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createDemoSession, decideAccessRequest, listAccessRequests } from "@/lib/api";
import { SessionProvider } from "@/lib/session";
import type { AccessRequest } from "@/lib/types";
import { PersonaPicker } from "./PersonaPicker";
import { SupervisorInbox } from "./SupervisorInbox";

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  createDemoSession: vi.fn(),
  listAccessRequests: vi.fn(),
  decideAccessRequest: vi.fn(),
}));

const pending: AccessRequest = {
  id: "ar-1",
  customer_id: "C-1017",
  fields: ["monthly_income", "current_debt"],
  purpose: "Evaluar renta y carga financiera para el crédito de consumo.",
  requested_by: "bruno",
  status: "pending",
  created_at: "2026-10-11T15:00:00Z",
  decided_by: null,
  decided_at: null,
  approved_fields: [],
};

const decided: AccessRequest = {
  ...pending,
  id: "ar-0",
  customer_id: "C-1009",
  fields: ["payment_behavior"],
  status: "approved",
  decided_by: "sofia",
  decided_at: "2026-10-11T14:10:00Z",
  approved_fields: ["payment_behavior"],
};

async function renderAs(persona: "sofia" | "ana") {
  vi.mocked(createDemoSession).mockResolvedValue(
    persona === "sofia" ? { token: "tok-sofia", name: "Sofía", role: "Supervisor" } : { token: "tok-ana", name: "Ana", role: "Asesor" },
  );
  render(
    <SessionProvider>
      <PersonaPicker />
      <SupervisorInbox />
    </SessionProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: /persona/i }));
  await userEvent.click(screen.getByRole("option", { name: persona === "sofia" ? /Sofía/ : /Ana/ }));
}

const card = async (customer: string) => (await screen.findByRole("heading", { name: new RegExp(customer) })).closest("article")!;

beforeEach(() => {
  vi.mocked(listAccessRequests).mockReset().mockResolvedValue([pending, decided]);
  vi.mocked(decideAccessRequest).mockReset();
});

describe("SupervisorInbox", () => {
  it("asks for the Supervisor persona instead of loading for an Asesor", async () => {
    await renderAs("ana");
    expect(screen.getByText(/Elige a Sofía/)).toBeInTheDocument();
    expect(listAccessRequests).not.toHaveBeenCalled();
  });

  it("lists pending requests with advisor, purpose and every field preselected", async () => {
    await renderAs("sofia");
    const item = await card("C-1017");

    expect(listAccessRequests).toHaveBeenCalledWith("tok-sofia");
    expect(item).toHaveTextContent("Bruno");
    expect(item).toHaveTextContent(pending.purpose);
    expect(within(item).getByRole("checkbox", { name: "Renta mensual" })).toBeChecked();
    expect(within(item).getByRole("checkbox", { name: "Deuda vigente" })).toBeChecked();
  });

  it("approves only the fields left checked", async () => {
    vi.mocked(decideAccessRequest).mockResolvedValue({ ...pending, status: "partially_approved", approved_fields: ["monthly_income"] });
    await renderAs("sofia");
    const item = await card("C-1017");

    await userEvent.click(within(item).getByRole("checkbox", { name: "Deuda vigente" }));
    await userEvent.click(within(item).getByRole("button", { name: "Aprobar selección" }));

    expect(decideAccessRequest).toHaveBeenCalledWith("ar-1", { approved_fields: ["monthly_income"] }, "tok-sofia");
  });

  it("rejects with no fields", async () => {
    vi.mocked(decideAccessRequest).mockResolvedValue({ ...pending, status: "rejected" });
    await renderAs("sofia");
    const item = await card("C-1017");

    await userEvent.click(within(item).getByRole("button", { name: "Rechazar" }));

    expect(decideAccessRequest).toHaveBeenCalledWith("ar-1", { approved_fields: [] }, "tok-sofia");
  });

  it("says the request was already decided on 409", async () => {
    vi.mocked(decideAccessRequest).mockRejectedValue(new ApiError(409));
    await renderAs("sofia");
    const item = await card("C-1017");

    await userEvent.click(within(item).getByRole("button", { name: "Rechazar" }));

    expect(await within(item).findByRole("alert")).toHaveTextContent("Ya decidida");
  });

  it("shows decided requests in the history", async () => {
    await renderAs("sofia");
    const history = await screen.findByRole("table", { name: "Historial de decisiones" });
    expect(within(history).getByText("C-1009")).toBeInTheDocument();
    expect(within(history).getByText("Aprobada")).toBeInTheDocument();
  });
});
