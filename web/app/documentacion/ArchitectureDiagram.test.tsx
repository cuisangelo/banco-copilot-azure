import { existsSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ArchitectureDiagram } from "./ArchitectureDiagram";
import { RESOURCE_GROUP_URL, RESOURCES, portalUrl } from "./azure";

const PUBLIC_DIR = join(import.meta.dirname, "../../public");

describe("ArchitectureDiagram", () => {
  it("is a navigable map: every deployed resource opens its portal page", () => {
    render(<ArchitectureDiagram />);
    for (const r of RESOURCES) {
      const node = screen.getByRole("link", { name: `Abrir ${r.name} en el portal de Azure` });
      expect(node).toHaveAttribute("href", portalUrl(r.type, r.name));
    }
  });

  it("opens the resource group from its boundary", () => {
    render(<ArchitectureDiagram />);
    expect(screen.getByRole("link", { name: "Abrir el grupo de recursos bcopilot-rg en el portal de Azure" })).toHaveAttribute(
      "href",
      `${RESOURCE_GROUP_URL}/overview`,
    );
  });

  it("only references icons that ship in public/azure-icons", () => {
    const { container } = render(<ArchitectureDiagram />);
    const icons = [...container.querySelectorAll("image")].map((image) => image.getAttribute("href")!);
    expect(icons.length).toBeGreaterThanOrEqual(RESOURCES.length);
    for (const icon of icons) {
      expect(icon).toMatch(/^\/azure-icons\/[a-z0-9-]+\.svg$/);
      expect(existsSync(`${PUBLIC_DIR}${icon}`), icon).toBe(true);
    }
  });
});
