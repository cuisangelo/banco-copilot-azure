import { describe, expect, it } from "vitest";
import fixture from "./__fixtures__/inventory.json";
import { portalUrl, resolveDeployment } from "./azure";

const clone = () => structuredClone(fixture);

describe("resolveDeployment", () => {
  it("joins the inventory with the copy for each resource", () => {
    const deployment = resolveDeployment(fixture);
    const cosmos = deployment.resources.find((r) => r.key === "cosmos")!;
    expect(cosmos).toMatchObject({ name: "demo-cosmos", service: "Azure Cosmos DB", icon: "cosmos-db.svg" });
    expect(deployment.resourceGroupUrl).toBe(
      "https://portal.azure.com/#@demo.onmicrosoft.com/resource/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/demo-rg",
    );
    expect(portalUrl(deployment, cosmos)).toBe(
      `${deployment.resourceGroupUrl}/providers/Microsoft.DocumentDB/databaseAccounts/demo-cosmos/overview`,
    );
  });

  it("rejects an inventory missing a resource the page draws", () => {
    const inventory = clone();
    inventory.resources = inventory.resources.filter((r) => r.key !== "search");
    expect(() => resolveDeployment(inventory)).toThrow(/search/);
  });

  it("rejects a resource the page has no copy for", () => {
    const inventory = clone();
    inventory.resources.push({ key: "redis", name: "demo-redis", type: "Microsoft.Cache/redis", location: "canadaeast" });
    expect(() => resolveDeployment(inventory)).toThrow(/redis/);
  });

  it("rejects a region the page cannot name", () => {
    const inventory = clone();
    inventory.resources[0].location = "westeurope";
    expect(() => resolveDeployment(inventory)).toThrow(/westeurope/);
  });
});
