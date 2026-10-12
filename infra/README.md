# Infraestructura (Terraform)

Toda la plataforma de Banco Copilot en una sola región (`canadaeast`), salvo Static Web Apps, que no
existe ahí y va en `eastus2`. Providers: `azurerm ~> 4` para casi todo y `azapi ~> 2` para el recurso
Foundry (`AIServices`), su proyecto, los deployments de modelos y la conexión a App Insights.

| Archivo | Contenido |
|---|---|
| `main.tf` | Grupo de recursos y sufijo aleatorio para los nombres globales |
| `security.tf` | Una identidad administrada por servicio, Key Vault (RBAC), secretos, asignaciones de rol, identidad de deploy para GitHub |
| `ai.tf` | Foundry, proyecto, `gpt-4.1-mini` (GlobalStandard, 50K TPM), `text-embedding-3-small` (100K TPM), Content Safety S0 |
| `search.tf` | AI Search `free` con semántica `free`. El índice `bank-docs` lo crea `scripts/ingest_local.py` |
| `data.tf` | Cosmos (free tier, 1000 RU/s compartidos) con los seis contenedores de los contratos; Storage con `docs` |
| `compute.tf` | ACR Basic, entorno de ACA, las cuatro apps, Static Web App Free |
| `apim.tf` | APIM Consumption, APIs `products` y `customers`, policy `X-Backend-Secret`, suscripción de `mcp-bank` |
| `ingest.tf` | Function Flex Consumption (Python 3.12) y Event Grid sobre el contenedor `docs` |
| `observability.tf` | Log Analytics, App Insights, conexión al proyecto Foundry y workbook |
| `budget.tf` | Budget mensual con alertas en USD 50 y USD 100 |
| `tests/` | Tests offline de invariantes (`terraform test`, providers mockeados) |

## Uso

```sh
az login
export ARM_SUBSCRIPTION_ID=<id de la suscripción>   # ambos providers fallan sin esto

terraform -chdir=infra init
terraform -chdir=infra test                           # offline, no toca Azure
terraform -chdir=infra validate
terraform -chdir=infra plan -out tfplan
```

`terraform.tfvars` no se commitea (está en `infra/.gitignore`):

```hcl
prefix              = "bcopilot"
daily_token_cap     = 200000
budget_alert_emails = ["alguien@example.com"]
```

### El apply va en dos fases

La suscripción de Event Grid apunta al webhook de la extensión de blobs de la Function. Ese webhook
solo responde al handshake de validación cuando el código de la Function ya está desplegado. Por eso:

1. `terraform apply tfplan`: crea todo menos la suscripción de Event Grid.
2. Desplegar el código: workflow `deploy` o `func azure functionapp publish`.
3. `terraform apply -var ingest_trigger_enabled=true`: crea la suscripción.

Hasta el paso 3, la ingesta se hace con `scripts/ingest_local.py`. Quien corre Terraform recibe los
roles que ese script necesita: Search Service Contributor, Search Index Data Contributor, OpenAI User
y Storage Blob Data Contributor.

### Despliegue desde GitHub (OIDC)

Terraform crea la identidad `*-github-deploy-id`, con AcrPush, Contributor sobre cada container app y
Website Contributor sobre la Function. La credencial federada se crea cuando existe el repo remoto:

```sh
terraform -chdir=infra apply -var github_repository=<owner>/<repo>
terraform -chdir=infra output github_deploy   # copiar cada clave como *secret* del repo en GitHub (los logs son públicos)
```

Las imágenes arrancan con `mcr.microsoft.com/k8se/quickstart` como placeholder. Terraform ignora los
cambios de imagen, así que `deploy.yml` puede rotar revisiones sin que el siguiente `plan` las revierta.

## Decisiones y desvíos respecto del plan

- **Rate limit en APIM:** `rate-limit-by-key` no existe en el tier Consumption (solo Developer, Basic,
  Standard, Premium y v2). Se usa `rate-limit` por suscripción: 120 llamadas/min. El límite por IP
  del público (10 req/min) sigue en `copilot-api`.
- **Connection string de App Insights:** va como variable de entorno normal, no por Key Vault. Microsoft
  aclara que no es una credencial: solo permite enviar telemetría.
- **`AZURE_CLIENT_ID`:** cada app y la Function lo reciben con el client id de su identidad. Sin él,
  `DefaultAzureCredential` no sabe qué identidad asignada por el usuario debe usar.
- **Key Vault:** cada identidad tiene *Key Vault Secrets User* sobre el secreto puntual que lee, no
  sobre la bóveda. Los secretos (incluida la llave RSA de personas) quedan en el state local de
  Terraform, que está ignorado por git.
- **Cosmos:** `local_authentication_enabled = false`. Los servicios usan el rol de datos *Built-in Data
  Contributor* con alcance a cada contenedor: `copilot-api` sobre `sessions`, `checkpoints`,
  `access_requests`, `audit` y `usage`; `customers-api` sobre `grants` y `audit`.
- **`max_replicas = 1`:** mantiene exacto el rate limit en memoria de `copilot-api`. Todas las apps
  escalan a cero.

## Riesgos abiertos (solo se confirman con `apply`)

- **Function Flex en Free Trial:** Flex aparece como disponible en `canadaeast`
  (`az functionapp list-flexconsumption-locations`), pero la creación no se probó. Si falla, el plan B
  es un Container Apps Job con el mismo código, disparado por una cola de Storage que recibe el
  `BlobCreated` de Event Grid. Hay que cambiar el trigger de WP2 de blob a queue.
- **Semántica `free` en AI Search Free:** el `plan` la acepta y la documentación se contradice. Si el
  apply la rechaza, se quita `semantic_search_sku` y la búsqueda queda híbrida sin reranking (spec §11).
- **Placeholder en el puerto 80:** la imagen quickstart escucha en 80 y las apps declaran
  `target_port = 8000`. Si ACA exige una revisión sana para dar el recurso por creado, el primer apply
  puede quedar esperando. En ese caso se despliegan las imágenes reales y se reintenta.
- **Free tier de Cosmos:** se permite una sola cuenta free por suscripción.
