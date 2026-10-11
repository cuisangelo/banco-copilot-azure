// Deployed inventory. Imported only by server components: scripts/check-public-bundle.mjs fails the build
// if any of these names reaches a file outside the auth-protected /documentacion route.

export const SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000000";
const TENANT_DOMAIN = "example.onmicrosoft.com";
const RESOURCE_GROUP = "bcopilot-rg";

export const RESOURCE_GROUP_URL = `https://portal.azure.com/#@${TENANT_DOMAIN}/resource/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}`;

export const portalUrl = (type: string, name: string) => `${RESOURCE_GROUP_URL}/providers/${type}/${name}/overview`;

export type Region = "canadaeast" | "eastus2";

export const REGION_LABEL: Record<Region, string> = {
  canadaeast: "Canada East",
  eastus2: "East US 2",
};

export type AzureResource = {
  name: string;
  type: string;
  service: string;
  // File in public/azure-icons, copied unmodified from the Microsoft Azure Architecture Icons.
  icon: string;
  region: Region;
  role: string;
};

export const RESOURCES: AzureResource[] = [
  {
    name: "bcopilot-copilot-api",
    type: "Microsoft.App/containerApps",
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    region: "canadaeast",
    role: "Frontera pública: personas demo, chat por SSE, solicitudes de acceso y el workflow de Agent Framework.",
  },
  {
    name: "bcopilot-mcp-bank",
    type: "Microsoft.App/containerApps",
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    region: "canadaeast",
    role: "Servidor MCP con tools de solo lectura. Ingress interno; reenvía el JWT de la persona a APIM.",
  },
  {
    name: "bcopilot-products-api",
    type: "Microsoft.App/containerApps",
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    region: "canadaeast",
    role: "API simulada de productos: tasas, comisiones y requisitos vigentes.",
  },
  {
    name: "bcopilot-customers-api",
    type: "Microsoft.App/containerApps",
    service: "Azure Container Apps",
    icon: "container-apps.svg",
    region: "canadaeast",
    role: "API simulada de clientes. Valida el JWT, aplica niveles y permisos por campo, y audita cada lectura.",
  },
  {
    name: "bcopilot-xxxxx-env",
    type: "Microsoft.App/managedEnvironments",
    service: "Container Apps Environment",
    icon: "container-apps-environment.svg",
    region: "canadaeast",
    role: "Aloja las cuatro apps con perfil Consumption; escalan a cero sin tráfico.",
  },
  {
    name: "bcopilot-xxxxx-foundry",
    type: "Microsoft.CognitiveServices/accounts",
    service: "Azure OpenAI en Foundry",
    icon: "openai.svg",
    region: "canadaeast",
    role: "Deployments gpt-4.1-mini para el chat y text-embedding-3-small para los embeddings.",
  },
  {
    name: "bcopilot-xxxxx-safety-eastus2",
    type: "Microsoft.CognitiveServices/accounts",
    service: "Azure AI Content Safety",
    icon: "content-safety.svg",
    region: "eastus2",
    role: "Prompt Shields sobre la consulta y los documentos, y groundedness sobre la respuesta.",
  },
  {
    name: "bcopilot-xxxxx-search",
    type: "Microsoft.Search/searchServices",
    service: "Azure AI Search",
    icon: "ai-search.svg",
    region: "canadaeast",
    role: "Índice bank-docs con búsqueda híbrida y reranking semántico.",
  },
  {
    name: "bcopilot-xxxxx-cosmos",
    type: "Microsoft.DocumentDB/databaseAccounts",
    service: "Azure Cosmos DB",
    icon: "cosmos-db.svg",
    region: "eastus2",
    role: "Sesiones, checkpoints, solicitudes de acceso, permisos con TTL, auditoría y uso diario de tokens.",
  },
  {
    name: "bcopilot-xxxxx-apim",
    type: "Microsoft.ApiManagement/service",
    service: "API Management",
    icon: "api-management.svg",
    region: "canadaeast",
    role: "Gateway Consumption hacia products-api y customers-api; inyecta X-Backend-Secret desde Key Vault.",
  },
  {
    name: "bcopilot-xxxxx-kv",
    type: "Microsoft.KeyVault/vaults",
    service: "Azure Key Vault",
    icon: "key-vault.svg",
    region: "canadaeast",
    role: "Llave de firma de las personas demo, secreto de backend y subscription key de APIM.",
  },
  {
    name: "bcopilot-xxxxx-appi",
    type: "Microsoft.Insights/components",
    service: "Application Insights",
    icon: "app-insights.svg",
    region: "canadaeast",
    role: "Trazas OpenTelemetry por nodo: modelo, tokens, latencia y costo estimado.",
  },
  {
    name: "bcopilot-xxxxx-logs",
    type: "Microsoft.OperationalInsights/workspaces",
    service: "Log Analytics",
    icon: "log-analytics.svg",
    region: "canadaeast",
    role: "Workspace que respalda a Application Insights.",
  },
  {
    name: "bcopilotxxxxxacr",
    type: "Microsoft.ContainerRegistry/registries",
    service: "Container Registry",
    icon: "container-registry.svg",
    region: "canadaeast",
    role: "Registro Basic con las imágenes de los cuatro servicios.",
  },
  {
    name: "bcopilotxxxxxst",
    type: "Microsoft.Storage/storageAccounts",
    service: "Storage Account",
    icon: "storage-accounts.svg",
    region: "canadaeast",
    role: "Contenedor docs con los documentos que alimentan la ingesta.",
  },
  {
    name: "bcopilot-xxxxx-storage-events",
    type: "Microsoft.EventGrid/systemTopics",
    service: "Event Grid System Topic",
    icon: "event-grid.svg",
    region: "canadaeast",
    role: "Avisa a la ingesta cada vez que llega un documento al contenedor docs.",
  },
  {
    name: "bcopilot-xxxxx-ingest",
    type: "Microsoft.Web/sites",
    service: "Azure Functions (Flex)",
    icon: "function-apps.svg",
    region: "canadaeast",
    role: "Divide por sección, genera embeddings y actualiza el índice de AI Search.",
  },
  {
    name: "bcopilot-xxxxx-web",
    type: "Microsoft.Web/staticSites",
    service: "Static Web Apps",
    icon: "static-web-apps.svg",
    region: "eastus2",
    role: "Este sitio: export estático de Next.js, con autenticación integrada para esta página.",
  },
];
