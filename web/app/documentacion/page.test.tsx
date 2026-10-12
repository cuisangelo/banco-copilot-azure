import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import fixture from "./__fixtures__/inventory.json";
import { stubSession } from "./__fixtures__/portal";
import DocumentationPage from "./page";
import { LOGIN_URL, PortalProvider } from "./portal";

vi.mock("./inventory", async () => {
  const { resolveDeployment, toLayout } = await import("./azure");
  const { default: fixture } = await import("./__fixtures__/inventory.json");
  return { loadLayout: () => toLayout(resolveDeployment(fixture)) };
});

function renderPage(owner: boolean) {
  stubSession(owner);
  return render(
    <PortalProvider>
      <DocumentationPage />
    </PortalProvider>,
  );
}

const PORTAL_RG =
  "https://portal.azure.com/#@demo.onmicrosoft.com/resource/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo-rg";

describe("/documentacion", () => {
  it("renders the product summary and a way back to the copilot", () => {
    renderPage(false);
    expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Probar el copiloto" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", LOGIN_URL);
  });

  it("draws the architecture and the workflow graph", () => {
    renderPage(false);
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

  it("contrasts the two retrieval modes", () => {
    renderPage(false);
    const section = screen.getByRole("region", { name: "Búsqueda: híbrida o agéntica" });
    expect(within(section).getAllByRole("heading", { level: 3 }).map((h) => h.textContent)).toEqual([
      "RAG híbridohybrid",
      "Agénticaagentic",
    ]);
  });

  it("shows anyone every resource without its name, id or portal link", async () => {
    renderPage(false);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalledWith("/.auth/me"));
    const list = screen.getByRole("list", { name: "Recursos desplegados" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(18);
    expect(within(list).queryAllByRole("link")).toHaveLength(0);
    for (const r of fixture.resources) expect(document.body.textContent).not.toContain(r.name);
    expect(document.body.textContent).not.toContain(fixture.subscriptionId);
    expect(screen.getByRole("link", { name: "Iniciar sesión para abrir en Azure" })).toHaveAttribute("href", LOGIN_URL);
  });

  it("links every deployed resource to its own page in the Azure portal for the owner", async () => {
    renderPage(true);
    await screen.findByRole("link", { name: /Grupo de recursos/ });
    const rows = within(screen.getByRole("list", { name: "Recursos desplegados" })).getAllByRole("listitem");
    expect(rows).toHaveLength(18);
    for (const row of rows) {
      const name = within(row).getByRole("heading").textContent!;
      const href = within(row).getByRole("link", { name: /Ver en Azure/ }).getAttribute("href")!;
      expect(href.startsWith(`${PORTAL_RG}/providers/`)).toBe(true);
      expect(href.endsWith(`/${name}/overview`)).toBe(true);
    }
  });

  it("points a resource at the provider type it actually is", async () => {
    renderPage(true);
    const cosmos = (await screen.findByRole("heading", { name: "demo-cosmos" })).closest("li")!;
    expect(within(cosmos).getByRole("link", { name: /Ver en Azure/ })).toHaveAttribute(
      "href",
      `${PORTAL_RG}/providers/Microsoft.DocumentDB/databaseAccounts/demo-cosmos/overview`,
    );
  });

  it("links the resource group for the owner and offers sign-out", async () => {
    renderPage(true);
    expect(await screen.findByRole("link", { name: /Grupo de recursos/ })).toHaveAttribute("href", `${PORTAL_RG}/overview`);
    expect(screen.getByRole("link", { name: "Cerrar sesión" })).toHaveAttribute(
      "href",
      "/.auth/logout?post_logout_redirect_uri=/documentacion",
    );
  });

  it("links the public key anyone can verify", () => {
    renderPage(false);
    expect(screen.getByRole("link", { name: "llave pública de las personas demo" })).toHaveAttribute(
      "href",
      "http://api.test/.well-known/jwks.json",
    );
  });
});
