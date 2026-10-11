import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { createDemoSession } from "@/lib/api";
import { SessionProvider, useSession } from "@/lib/session";
import { PersonaPicker } from "./PersonaPicker";

vi.mock("@/lib/api", () => ({ createDemoSession: vi.fn() }));

let expire: () => void;
function ExpireHandle() {
  expire = useSession().expire;
  return null;
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

    act(() => expire());

    expect(screen.getByRole("alert")).toHaveTextContent(/venció/);
    expect(screen.getByRole("listbox")).toBeVisible();
    expect(screen.getByRole("button", { name: /persona/i })).toHaveTextContent("Sin persona");
  });
});
