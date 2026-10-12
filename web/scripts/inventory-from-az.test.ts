import { describe, expect, it } from "vitest";
import fixture from "@/app/documentacion/__fixtures__/inventory.json";
import { CATALOG } from "@/app/documentacion/azure";
import { buildInventory, RULES } from "./inventory-from-az.mjs";

const account = { id: fixture.subscriptionId, tenantDefaultDomain: fixture.tenantDomain };

// Shaped like `az resource list -o json`: extra fields, resources the diagram does not draw, and the
// lowercase types az returns for some providers.
const azResources = [
  ...fixture.resources.map(({ name, type, location }) => ({ id: `/x/${name}`, name, type, location, tags: {} })),
  { name: "demo-copilot-api-id", type: "Microsoft.ManagedIdentity/userAssignedIdentities", location: "canadaeast" },
  { name: "demo-foundry/demo-project", type: "Microsoft.CognitiveServices/accounts/projects", location: "canadaeast" },
  { name: "Application Insights Smart Detection", type: "microsoft.insights/actiongroups", location: "global" },
  { name: "demo-ingest-plan", type: "Microsoft.Web/serverFarms", location: "canadaeast" },
];

describe("buildInventory", () => {
  it("maps az output to the inventory the page renders", () => {
    expect(buildInventory(account, azResources, "demo-rg")).toEqual(fixture);
  });

  it("is deterministic regardless of the order az returns", () => {
    expect(buildInventory(account, [...azResources].reverse(), "demo-rg")).toEqual(fixture);
  });

  it("matches type case-insensitively", () => {
    const lowercased = azResources.map((r) => ({ ...r, type: r.type.toLowerCase() }));
    expect(buildInventory(account, lowercased, "demo-rg").resources.map((r) => r.type)).toEqual(
      fixture.resources.map((r) => r.type),
    );
  });

  it("fails when a drawn resource is missing", () => {
    const withoutCosmos = azResources.filter((r) => r.name !== "demo-cosmos");
    expect(() => buildInventory(account, withoutCosmos, "demo-rg")).toThrow(/cosmos/);
  });

  it("fails when a resource cannot be told apart from another of its type", () => {
    const extra = [...azResources, { name: "demo-reports-api", type: "Microsoft.App/containerApps", location: "canadaeast" }];
    expect(() => buildInventory(account, extra, "demo-rg")).toThrow(/demo-reports-api/);
  });

  it("fails when two resources claim the same key", () => {
    const twice = [...azResources, { name: "demo-search-2", type: "Microsoft.Search/searchServices", location: "canadaeast" }];
    expect(() => buildInventory(account, twice, "demo-rg")).toThrow(/search/);
  });

  it("leaves out the agentic search service that exists only during demos", () => {
    const withAgentic = [...azResources, { name: "demo-agentic-search", type: "Microsoft.Search/searchServices", location: "canadaeast" }];
    expect(buildInventory(account, withAgentic, "demo-rg")).toEqual(fixture);
  });

  it("fails when the account lacks the tenant domain", () => {
    expect(() => buildInventory({ id: account.id }, azResources, "demo-rg")).toThrow(/tenantDefaultDomain/);
  });

  it("knows exactly the resources the page has copy for", () => {
    expect(RULES.map((rule: { key: string }) => rule.key).sort()).toEqual(Object.keys(CATALOG).sort());
  });
});
