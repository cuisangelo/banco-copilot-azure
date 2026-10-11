// What the page says about each deployed resource, keyed by a stable logical key. Names, subscription and
// tenant come from inventory.generated.json (scripts/web_inventory.sh), which is gitignored: the repo is
// public and carries no identifier of the real deployment.

export type Region = "canadaeast" | "eastus2";

const REGION_LABEL: Record<Region, string> = {
  canadaeast: "Canada East",
  eastus2: "East US 2",
};

type Copy = {
  service: string;
  // File in public/azure-icons, copied unmodified from the Microsoft Azure Architecture Icons.
  icon: string;
  role: string;
};

export const CATALOG = {
  "copilot-api": {
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    role: "Frontera pública: personas demo, chat por SSE, solicitudes de acceso y el workflow de Agent Framework.",
  },
  "mcp-bank": {
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    role: "Servidor MCP con tools de solo lectura. Ingress interno; reenvía el JWT de la persona a APIM.",
  },
  "products-api": {
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    role: "API simulada de productos: tasas, comisiones y requisitos vigentes.",
  },
  "customers-api": {
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    role: "API simulada de clientes. Valida el JWT, aplica niveles y permisos por campo, y audita cada lectura.",
  },
  "container-apps-env": {
    service: "Container Apps Environment",
    icon: "container-apps-environment.svg",
    role: "Aloja las cuatro apps con perfil Consumption; escalan a cero sin tráfico.",
  },
  foundry: {
    service: "Azure OpenAI en Foundry",
    icon: "openai.svg",
    role: "Deployments gpt-4.1-mini para el chat y text-embedding-3-small para los embeddings.",
  },
  "content-safety": {
    service: "Azure AI Content Safety",
    icon: "content-safety.svg",
    role: "Prompt Shields sobre la consulta y los documentos, y groundedness sobre la respuesta.",
  },
  search: {
    service: "Azure AI Search",
    icon: "ai-search.svg",
    role: "Índice bank-docs con búsqueda híbrida y reranking semántico.",
  },
  cosmos: {
    service: "Azure Cosmos DB",
    icon: "cosmos-db.svg",
    role: "Sesiones, checkpoints, solicitudes de acceso, permisos con TTL, auditoría y uso diario de tokens.",
  },
  apim: {
    service: "API Management",
    icon: "api-management.svg",
    role: "Gateway Consumption hacia products-api y customers-api; inyecta X-Backend-Secret desde Key Vault.",
  },
  "key-vault": {
    service: "Azure Key Vault",
    icon: "key-vault.svg",
    role: "Llave de firma de las personas demo, secreto de backend y subscription key de APIM.",
  },
  "app-insights": {
    service: "Application Insights",
    icon: "app-insights.svg",
    role: "Trazas OpenTelemetry por nodo: modelo, tokens, latencia y costo estimado.",
  },
  "log-analytics": {
    service: "Log Analytics",
    icon: "log-analytics.svg",
    role: "Workspace que respalda a Application Insights.",
  },
  "container-registry": {
    service: "Container Registry",
    icon: "container-registry.svg",
    role: "Registro Basic con las imágenes de los cuatro servicios.",
  },
  storage: {
    service: "Storage Account",
    icon: "storage-accounts.svg",
    role: "Contenedor docs con los documentos que alimentan la ingesta.",
  },
  "storage-events": {
    service: "Event Grid System Topic",
    icon: "event-grid.svg",
    role: "Avisa a la ingesta cada vez que llega un documento al contenedor docs.",
  },
  ingest: {
    service: "Azure Functions (Flex)",
    icon: "function-apps.svg",
    role: "Divide por sección, genera embeddings y actualiza el índice de AI Search.",
  },
  web: {
    service: "Static Web Apps",
    icon: "static-web-apps.svg",
    role: "Este sitio: export estático de Next.js, con autenticación integrada para esta página.",
  },
} satisfies Record<string, Copy>;

export type ResourceKey = keyof typeof CATALOG;

export type Inventory = {
  subscriptionId: string;
  tenantDomain: string;
  resourceGroup: string;
  resources: { key: string; name: string; type: string; location: string }[];
};

export type AzureResource = Copy & {
  key: ResourceKey;
  name: string;
  type: string;
  location: Region;
  regionLabel: string;
};

export type Deployment = {
  resourceGroup: string;
  resourceGroupUrl: string;
  resources: AzureResource[];
};

const isKey = (key: string): key is ResourceKey => Object.hasOwn(CATALOG, key);
const isRegion = (location: string): location is Region => Object.hasOwn(REGION_LABEL, location);

export function resolveDeployment(inventory: Inventory): Deployment {
  const resources = inventory.resources.map(({ key, name, type, location }) => {
    if (!isKey(key)) throw new Error(`inventory: no copy for resource key "${key}" (${name})`);
    if (!isRegion(location)) throw new Error(`inventory: no label for region "${location}" (${name})`);
    return { key, name, type, location, regionLabel: REGION_LABEL[location], ...CATALOG[key] };
  });
  for (const key of Object.keys(CATALOG)) {
    const count = resources.filter((r) => r.key === key).length;
    if (count !== 1) throw new Error(`inventory: expected one "${key}" resource, found ${count}`);
  }
  const { tenantDomain, subscriptionId, resourceGroup } = inventory;
  return {
    resourceGroup,
    resourceGroupUrl: `https://portal.azure.com/#@${tenantDomain}/resource/subscriptions/${subscriptionId}/resourceGroups/${resourceGroup}`,
    resources,
  };
}

export const portalUrl = (deployment: Deployment, resource: Pick<AzureResource, "type" | "name">) =>
  `${deployment.resourceGroupUrl}/providers/${resource.type}/${resource.name}/overview`;

export function resourceByKey(deployment: Deployment, key: ResourceKey): AzureResource {
  // resolveDeployment guarantees exactly one resource per key.
  return deployment.resources.find((r) => r.key === key)!;
}
