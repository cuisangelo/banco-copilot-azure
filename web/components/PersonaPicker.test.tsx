import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, createDemoSession } from "@/lib/api";
import { SessionProvider, useSession } from "@/lib/session";
import { PersonaPicker } from "./PersonaPicker";

vi.mock("@/lib/api", async (importOriginal) => ({
  ApiError: (await importOriginal<typeof import("@/lib/api")>()).ApiError,
  createDemoSession: vi.fn(),
}));

function ExpireHandle() {
  return <button onClick={useSession().expire}>simular 401</button>;
}

function renderPicker() {
  render(
    <SessionProvider>
      <PersonaPicker />
      <ExpireHandle />
    </SessionProvider>,
  );
}

beforeEach(() => {
  vi.mocked(createDemoSession).mockReset();
  vi.mocked(createDemoSession).mockResolvedValue({ token: "tok-ana", name: "Ana", role: "Asesor" });
});

describe("PersonaPicker", () => {
  it("starts without a persona", () => {
    renderPicker();
    expect(screen.getByRole("button", { name: /persona/i })).toHaveTextContent("Sin persona");
  });

  it("signs in as the chosen persona and shows name and role", async () => {
    renderPicker();
    await userEvent.click(screen.getByRole("button", { name: /persona/i }));
    await userEvent.click(screen.getByRole("option", { name: /Ana/ }));

    expect(createDemoSession).toHaveBeenCalledWith("ana");
    const trigger = screen.getByRole("button", { name: /persona/i });
    expect(trigger).toHaveTextContent("Ana");
    expect(trigger).toHaveTextContent("Asesor");
  });

  it("keeps the token out of browser storage", async () => {
    renderPicker();
    await userEvent.click(screen.getByRole("button", { name: /persona/i }));
    await userEvent.click(screen.getByRole("option", { name: /Ana/ }));

    expect(localStorage.length).toBe(0);
    expect(sessionStorage.length).toBe(0);
  });

  it("returns to the picker with a notice when the session expires", async () => {
    renderPicker();
    await userEvent.click(screen.getByRole("button", { name: /persona/i }));
    await userEvent.click(screen.getByRole("option", { name: /Ana/ }));

    await userEvent.click(screen.getByRole("button", { name: "simular 401" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/venció/);
    expect(screen.getByRole("listbox")).toBeVisible();
    expect(screen.getByRole("button", { name: /persona/i })).toHaveTextContent("Sin persona");
  });
});

describe("PersonaPicker against a scaled-to-zero API", () => {
  function renderWithInstantRetries() {
    render(
      <SessionProvider retryDelaysMs={[0, 0, 0]}>
        <PersonaPicker />
      </SessionProvider>,
    );
  }

  it("retries while the server wakes up and then signs in", async () => {
    vi.mocked(createDemoSession)
      .mockRejectedValueOnce(new ApiError(503))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({ token: "tok-ana", name: "Ana", role: "Asesor" });
    renderWithInstantRetries();

    await userEvent.click(screen.getByRole("button", { name: /persona/i }));
    await userEvent.click(screen.getByRole("option", { name: /Ana/ }));

    expect(await screen.findByRole("button", { name: /Ana, Asesor/ })).toBeInTheDocument();
    expect(createDemoSession).toHaveBeenCalledTimes(3);
  });

  it("does not retry errors that are not a cold start", async () => {
    vi.mocked(createDemoSession).mockRejectedValue(new ApiError(400));
    renderWithInstantRetries();

    await userEvent.click(screen.getByRole("button", { name: /persona/i }));
    await userEvent.click(screen.getByRole("option", { name: /Ana/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/No se pudo iniciar/);
    expect(createDemoSession).toHaveBeenCalledTimes(1);
  });

  it("shows that it is connecting instead of closing silently", async () => {
    vi.mocked(createDemoSession).mockReturnValue(new Promise(() => {}));
    renderWithInstantRetries();

    await userEvent.click(screen.getByRole("button", { name: /persona/i }));
    await userEvent.click(screen.getByRole("option", { name: /Ana/ }));

    expect(screen.getByRole("status")).toHaveTextContent(/Conectando/);
  });
});
