import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import SupervisorPage from "./page";

vi.mock("@/components/SupervisorInbox", () => ({ SupervisorInbox: () => <p>bandeja</p> }));
vi.mock("@/components/FeedbackPanel", () => ({ FeedbackPanel: () => <p>feedback</p> }));

describe("SupervisorPage", () => {
  it("opens on the inbox and switches to the Feedback tab", async () => {
    render(<SupervisorPage />);

    expect(screen.getByRole("tab", { name: "Solicitudes" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByText("bandeja")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("tab", { name: "Feedback" }));

    expect(screen.getByRole("tab", { name: "Feedback" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("feedback");
    expect(screen.queryByText("bandeja")).not.toBeInTheDocument();
  });
});
