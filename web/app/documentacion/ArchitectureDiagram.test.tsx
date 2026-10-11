import { existsSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/inventory.json";
import { ArchitectureDiagram } from "./ArchitectureDiagram";
import { portalUrl, resolveDeployment } from "./azure";

const PUBLIC_DIR = join(import.meta.dirname, "../../public");
const deployment = resolveDeployment(fixture);

describe("ArchitectureDiagram", () => {
  it("is a navigable map: every deployed resource opens its portal page", () => {
    render(<ArchitectureDiagram deployment={deployment} />);
    for (const r of deployment.resources) {
      const node = screen.getByRole("link", { name: `Abrir ${r.name} en el portal de Azure` });
      expect(node).toHaveAttribute("href", portalUrl(deployment, r));
    }
  });

  it("opens the resource group from its boundary", () => {
    render(<ArchitectureDiagram deployment={deployment} />);
    expect(screen.getByRole("link", { name: "Abrir el grupo de recursos demo-rg en el portal de Azure" })).toHaveAttribute(
      "href",
      `${deployment.resourceGroupUrl}/overview`,
    );
  });

  it("only references icons that ship in public/azure-icons", () => {
    const { container } = render(<ArchitectureDiagram deployment={deployment} />);
    const icons = [...container.querySelectorAll("image")].map((image) => image.getAttribute("href")!);
    expect(icons.length).toBeGreaterThanOrEqual(deployment.resources.length);
    for (const icon of icons) {
      expect(icon).toMatch(/^\/azure-icons\/[a-z0-9-]+\.svg$/);
      expect(existsSync(`${PUBLIC_DIR}${icon}`), icon).toBe(true);
    }
  });
});
