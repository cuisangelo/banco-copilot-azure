import { existsSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import fixture from "./__fixtures__/inventory.json";
import { stubSession } from "./__fixtures__/portal";
import { ArchitectureDiagram } from "./ArchitectureDiagram";
import { portalUrl, resolveDeployment, toLayout } from "./azure";
import { PortalProvider } from "./portal";

const PUBLIC_DIR = join(import.meta.dirname, "../../public");
const deployment = resolveDeployment(fixture);
const layout = toLayout(deployment);

function renderDiagram() {
  return render(
    <PortalProvider>
      <ArchitectureDiagram layout={layout} />
    </PortalProvider>,
  );
}

describe("ArchitectureDiagram", () => {
  it("shows anyone the map without resource names or portal links", async () => {
    const fetchMock = stubSession(false);
    const { container } = renderDiagram();

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/.auth/me"));
    expect(screen.queryAllByRole("link")).toHaveLength(0);
    for (const r of deployment.resources) expect(container.textContent).not.toContain(r.name);
    expect(screen.getByText("Azure Cosmos DB")).toBeInTheDocument();
  });

  it("is a navigable map for the owner: every deployed resource opens its portal page", async () => {
    stubSession(true);
    renderDiagram();

    for (const r of deployment.resources) {
      const node = await screen.findByRole("link", { name: `Abrir ${r.name} en el portal de Azure` });
      expect(node).toHaveAttribute("href", portalUrl(deployment, r));
    }
    expect(screen.getByRole("link", { name: "Abrir el grupo de recursos demo-rg en el portal de Azure" })).toHaveAttribute(
      "href",
      `${deployment.resourceGroupUrl}/overview`,
    );
  });

  it("only references icons that ship in public/azure-icons", () => {
    stubSession(false);
    const { container } = renderDiagram();
    const icons = [...container.querySelectorAll("image")].map((image) => image.getAttribute("href")!);
    expect(icons.length).toBeGreaterThanOrEqual(layout.resources.length);
    for (const icon of icons) {
      expect(icon).toMatch(/^\/azure-icons\/[a-z0-9-]+\.svg$/);
      expect(existsSync(`${PUBLIC_DIR}${icon}`), icon).toBe(true);
    }
  });
});
