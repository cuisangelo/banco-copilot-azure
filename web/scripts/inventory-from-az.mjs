// Turns `az account show` + `az resource list` into app/documentacion/inventory.generated.json.
// Called by scripts/web_inventory.sh: node inventory-from-az.mjs <resource-group> <account.json> <resources.json>
import { readFileSync } from "node:fs";

// One rule per resource the page draws, in display order. A type shared by several resources is told
// apart by the name suffix Terraform gives it.
export const RULES = [
  { key: "copilot-api", type: "Microsoft.App/containerApps", match: /-copilot-api$/ },
  { key: "mcp-bank", type: "Microsoft.App/containerApps", match: /-mcp-bank$/ },
  { key: "products-api", type: "Microsoft.App/containerApps", match: /-products-api$/ },
  { key: "customers-api", type: "Microsoft.App/containerApps", match: /-customers-api$/ },
  { key: "container-apps-env", type: "Microsoft.App/managedEnvironments" },
  { key: "foundry", type: "Microsoft.CognitiveServices/accounts", match: /-foundry$/ },
  { key: "content-safety", type: "Microsoft.CognitiveServices/accounts", match: /-safety(-|$)/ },
  { key: "search", type: "Microsoft.Search/searchServices" },
  { key: "cosmos", type: "Microsoft.DocumentDB/databaseAccounts" },
  { key: "apim", type: "Microsoft.ApiManagement/service" },
  { key: "key-vault", type: "Microsoft.KeyVault/vaults" },
  { key: "app-insights", type: "Microsoft.Insights/components" },
  { key: "log-analytics", type: "Microsoft.OperationalInsights/workspaces" },
  { key: "container-registry", type: "Microsoft.ContainerRegistry/registries" },
  { key: "storage", type: "Microsoft.Storage/storageAccounts" },
  { key: "storage-events", type: "Microsoft.EventGrid/systemTopics" },
  { key: "ingest", type: "Microsoft.Web/sites" },
  { key: "web", type: "Microsoft.Web/staticSites" },
];

const DRAWN_TYPES = new Set(RULES.map((rule) => rule.type.toLowerCase()));

export function buildInventory(account, azResources, resourceGroup) {
  if (!account.id) throw new Error("az account show: missing id");
  if (!account.tenantDefaultDomain) throw new Error("az account show: missing tenantDefaultDomain");

  const claimed = new Map();
  for (const resource of azResources) {
    const type = resource.type.toLowerCase();
    // Identities, Foundry projects, workbooks, plans and alert groups exist but are not drawn.
    if (!DRAWN_TYPES.has(type)) continue;
    const rules = RULES.filter((rule) => rule.type.toLowerCase() === type && (!rule.match || rule.match.test(resource.name)));
    if (rules.length !== 1) {
      throw new Error(`cannot map ${resource.name} (${resource.type}) to one drawn resource: ${rules.length} rules match`);
    }
    const { key } = rules[0];
    if (claimed.has(key)) throw new Error(`two resources for "${key}": ${claimed.get(key).name} and ${resource.name}`);
    claimed.set(key, resource);
  }

  const missing = RULES.filter((rule) => !claimed.has(rule.key)).map((rule) => rule.key);
  if (missing.length) throw new Error(`resource group ${resourceGroup} lacks: ${missing.join(", ")}`);

  return {
    subscriptionId: account.id,
    tenantDomain: account.tenantDefaultDomain,
    resourceGroup,
    resources: RULES.map(({ key, type }) => {
      const { name, location } = claimed.get(key);
      return { key, name, type, location };
    }),
  };
}

if (import.meta.main) {
  const [resourceGroup, accountPath, resourcesPath] = process.argv.slice(2);
  if (!resourcesPath) throw new Error("usage: inventory-from-az.mjs <resource-group> <account.json> <resources.json>");
  const read = (path) => JSON.parse(readFileSync(path, "utf8"));
  const inventory = buildInventory(read(accountPath), read(resourcesPath), resourceGroup);
  process.stdout.write(`${JSON.stringify(inventory, null, 2)}\n`);
}
