import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DocumentationPage from "./page";

vi.mock("./inventory", async () => {
  const { resolveDeployment } = await import("./azure");
  const { default: fixture } = await import("./__fixtures__/inventory.json");
  return { loadDeployment: () => resolveDeployment(fixture) };
});

const PORTAL_RG =
  "https://portal.azure.com/#@demo.onmicrosoft.com/resource/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo-rg";

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn().mockReturnValue(new Promise(() => {})));
});

describe("/documentacion", () => {
  it("renders the product summary and a way back to the copilot", () => {
    render(<DocumentationPage />);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Probar el copiloto" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Cerrar sesión" })).toHaveAttribute(
      "href",
      "/.auth/logout?post_logout_redirect_uri=/",
    );
  });

  it("draws the architecture and the workflow graph", () => {
    render(<DocumentationPage />);
    expect(screen.getByRole("group", { name: /arquitectura/i })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Flujo principal" })).getAllByRole("listitem").length).toBeGreaterThan(0);
    expect(screen.getByText("Íconos: Microsoft Azure Architecture Icons")).toBeInTheDocument();
    const steps = within(screen.getByRole("list", { name: "Nodos del workflow" })).getAllByRole("listitem");
    expect(steps.map((s) => s.dataset.node)).toEqual([
      "input_guard",
      "router",
      "rag_agent",
      "product_agent",
      "customer_agent",
      "composer",
      "verifier",
      "escalation",
    ]);
  });

  it("links every deployed resource to its own page in the Azure portal", () => {
    render(<DocumentationPage />);
    const rows = within(screen.getByRole("list", { name: "Recursos desplegados" })).getAllByRole("listitem");
    expect(rows).toHaveLength(18);
    for (const row of rows) {
      const name = within(row).getByRole("heading").textContent!;
      const href = within(row).getByRole("link", { name: /Ver en Azure/ }).getAttribute("href")!;
      expect(href.startsWith(`${PORTAL_RG}/providers/`)).toBe(true);
      expect(href.endsWith(`/${name}/overview`)).toBe(true);
    }
  });

  it("points a resource at the provider type it actually is", () => {
    render(<DocumentationPage />);
    const cosmos = screen.getByRole("heading", { name: "demo-cosmos" }).closest("li")!;
    expect(within(cosmos).getByRole("link", { name: /Ver en Azure/ })).toHaveAttribute(
      "href",
      `${PORTAL_RG}/providers/Microsoft.DocumentDB/databaseAccounts/demo-cosmos/overview`,
    );
  });

  it("links the resource group and warns that the portal needs access", () => {
    render(<DocumentationPage />);
    expect(screen.getByRole("link", { name: /Grupo de recursos/ })).toHaveAttribute("href", `${PORTAL_RG}/overview`);
    expect(screen.getByText("Los enlaces al portal requieren acceso a la suscripción del autor.")).toBeInTheDocument();
  });

  it("links the public key anyone can verify", () => {
    render(<DocumentationPage />);
    expect(screen.getByRole("link", { name: "llave pública de las personas demo" })).toHaveAttribute(
      "href",
      "http://api.test/.well-known/jwks.json",
    );
  });
});
