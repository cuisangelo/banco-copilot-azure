resource "azurerm_user_assigned_identity" "service" {
  for_each = setunion(local.services, ["ingest"])

  name                = "${local.name}-${each.key}-id"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_key_vault" "main" {
  name                       = "${local.name}-kv"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
}

resource "azurerm_role_assignment" "deployer_kv_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# A fresh role assignment takes up to a minute to be honoured by the data plane.
resource "time_sleep" "deployer_rbac" {
  depends_on      = [azurerm_role_assignment.deployer_kv_secrets_officer]
  create_duration = "60s"
}

resource "tls_private_key" "persona" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "random_password" "backend_secret" {
  length  = 48
  special = false
}

locals {
  secret_values = {
    "backend-secret"          = random_password.backend_secret.result
    "persona-private-key-pem" = tls_private_key.persona.private_key_pem
    "persona-public-key-pem"  = tls_private_key.persona.public_key_pem
    "apim-subscription-key"   = azurerm_api_management_subscription.mcp_bank.primary_key
  }
}

resource "azurerm_key_vault_secret" "secret" {
  # Keys are spelled out because for_each refuses a map with sensitive values.
  for_each = toset(["backend-secret", "persona-private-key-pem", "persona-public-key-pem", "apim-subscription-key"])

  name         = each.key
  value        = local.secret_values[each.key]
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [time_sleep.deployer_rbac]
}

locals {
  cosmos_data_contributor = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"

  # Least privilege per identity (spec §5). Key Vault roles are scoped to the single secret each reader needs.
  service_roles = merge(
    {
      for svc in local.services : "${svc}/acr-pull" => {
        principal_id = azurerm_user_assigned_identity.service[svc].principal_id
        role         = "AcrPull"
        scope        = azurerm_container_registry.main.id
      }
    },
    {
      for pair in [
        ["copilot-api", "apim-subscription-key"],
        ["copilot-api", "persona-private-key-pem"],
        ["mcp-bank", "apim-subscription-key"],
        ["products-api", "backend-secret"],
        ["customers-api", "backend-secret"],
        ["customers-api", "persona-public-key-pem"],
        ] : "${pair[0]}/kv/${pair[1]}" => {
        principal_id = azurerm_user_assigned_identity.service[pair[0]].principal_id
        role         = "Key Vault Secrets User"
        scope        = azurerm_key_vault_secret.secret[pair[1]].resource_versionless_id
      }
    },
    {
      "copilot-api/openai" = {
        principal_id = azurerm_user_assigned_identity.service["copilot-api"].principal_id
        role         = "Cognitive Services OpenAI User"
        scope        = azapi_resource.foundry.id
      }
      "copilot-api/content-safety" = {
        principal_id = azurerm_user_assigned_identity.service["copilot-api"].principal_id
        role         = "Cognitive Services User"
        scope        = azurerm_cognitive_account.content_safety.id
      }
      "copilot-api/search" = {
        principal_id = azurerm_user_assigned_identity.service["copilot-api"].principal_id
        role         = "Search Index Data Reader"
        scope        = azurerm_search_service.main.id
      }
      "ingest/openai" = {
        principal_id = azurerm_user_assigned_identity.service["ingest"].principal_id
        role         = "Cognitive Services OpenAI User"
        scope        = azapi_resource.foundry.id
      }
      "ingest/search-data" = {
        principal_id = azurerm_user_assigned_identity.service["ingest"].principal_id
        role         = "Search Index Data Contributor"
        scope        = azurerm_search_service.main.id
      }
      # The Flex host keeps its deployment package, leases and blob receipts in this account.
      "ingest/blob" = {
        principal_id = azurerm_user_assigned_identity.service["ingest"].principal_id
        role         = "Storage Blob Data Owner"
        scope        = azurerm_storage_account.main.id
      }
      # Blob triggers park poison blobs in a queue.
      "ingest/queue" = {
        principal_id = azurerm_user_assigned_identity.service["ingest"].principal_id
        role         = "Storage Queue Data Contributor"
        scope        = azurerm_storage_account.main.id
      }
      "apim/kv/backend-secret" = {
        principal_id = azurerm_api_management.main.identity[0].principal_id
        role         = "Key Vault Secrets User"
        scope        = azurerm_key_vault_secret.secret["backend-secret"].resource_versionless_id
      }
    },
    {
      for key, assignment in {
        "copilot-api/agentic-search" = {
          principal_id = azurerm_user_assigned_identity.service["copilot-api"].principal_id
          role         = "Search Index Data Reader"
          scope        = one(azurerm_search_service.agentic[*].id)
        }
        # The knowledge base's query planner calls the chat deployment as the search service.
        "agentic-search/openai" = {
          principal_id = one(azurerm_search_service.agentic[*].identity[0].principal_id)
          role         = "Cognitive Services OpenAI User"
          scope        = azapi_resource.foundry.id
        }
      } : key => assignment if var.agentic_search_enabled
    },
  )

  # The developer running scripts/ingest_local.py (which also creates the bank-docs index) authenticates with az login.
  deployer_roles = {
    "openai"         = { role = "Cognitive Services OpenAI User", scope = azapi_resource.foundry.id }
    "search-data"    = { role = "Search Index Data Contributor", scope = azurerm_search_service.main.id }
    "search-service" = { role = "Search Service Contributor", scope = azurerm_search_service.main.id }
    "blob"           = { role = "Storage Blob Data Contributor", scope = azurerm_storage_account.main.id }
  }
  # scripts/ingest_local.py and scripts/create_knowledge_base.py load the agentic service the same way.
  agentic_deployer_roles = {
    for key, role in {
      "agentic-search-data"    = "Search Index Data Contributor"
      "agentic-search-service" = "Search Service Contributor"
    } : key => { role = role, scope = one(azurerm_search_service.agentic[*].id) } if var.agentic_search_enabled
  }

  cosmos_roles = {
    "copilot-api/sessions"        = { svc = "copilot-api", container = "sessions" }
    "copilot-api/checkpoints"     = { svc = "copilot-api", container = "checkpoints" }
    "copilot-api/access_requests" = { svc = "copilot-api", container = "access_requests" }
    "copilot-api/audit"           = { svc = "copilot-api", container = "audit" }
    "copilot-api/usage"           = { svc = "copilot-api", container = "usage" }
    "customers-api/grants"        = { svc = "customers-api", container = "grants" }
    "customers-api/audit"         = { svc = "customers-api", container = "audit" }
  }
}

resource "azurerm_role_assignment" "service" {
  for_each = local.service_roles

  scope                = each.value.scope
  role_definition_name = each.value.role
  principal_id         = each.value.principal_id
  principal_type       = "ServicePrincipal"
}

resource "azurerm_role_assignment" "deployer" {
  for_each = merge(local.deployer_roles, local.agentic_deployer_roles)

  scope                = each.value.scope
  role_definition_name = each.value.role
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "azurerm_cosmosdb_sql_role_assignment" "service" {
  for_each = local.cosmos_roles

  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = local.cosmos_data_contributor
  principal_id        = azurerm_user_assigned_identity.service[each.value.svc].principal_id
  scope               = "${azurerm_cosmosdb_account.main.id}/dbs/${azurerm_cosmosdb_sql_database.copilot.name}/colls/${azurerm_cosmosdb_sql_container.container[each.value.container].name}"
}

resource "time_sleep" "service_rbac" {
  depends_on      = [azurerm_role_assignment.service]
  create_duration = "60s"
}

# GitHub Actions deploys through OIDC with this identity: push images and roll container app revisions.
resource "azurerm_user_assigned_identity" "github_deploy" {
  name                = "${local.name}-github-deploy-id"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_federated_identity_credential" "github_main" {
  count = var.github_repository == null ? 0 : 1

  name      = "github-main"
  parent_id = azurerm_user_assigned_identity.github_deploy.id
  audience  = ["api://AzureADTokenExchange"]
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = "repo:${var.github_repository}:ref:refs/heads/main"
}

# evals.yml runs on pull requests, whose OIDC subject differs from a branch push. GitHub does not
# issue OIDC tokens to pull requests from forks, so only branches of this repository can use it.
resource "azurerm_federated_identity_credential" "github_pull_request" {
  count = var.github_repository == null ? 0 : 1

  name      = "github-pull-request"
  parent_id = azurerm_user_assigned_identity.github_deploy.id
  audience  = ["api://AzureADTokenExchange"]
  issuer    = "https://token.actions.githubusercontent.com"
  subject   = "repo:${var.github_repository}:pull_request"
}

resource "azurerm_role_assignment" "github_deploy" {
  for_each = merge(
    { "acr-push" = { role = "AcrPush", scope = azurerm_container_registry.main.id } },
    { for svc in local.services : "app/${svc}" => { role = "Contributor", scope = azurerm_container_app.app[svc].id } },
    { "ingest-function" = { role = "Website Contributor", scope = azurerm_function_app_flex_consumption.ingest.id } },
    # evals.yml: the LLM judges call the chat deployment and the run is uploaded to the Foundry project.
    { "evals-openai" = { role = "Cognitive Services OpenAI User", scope = azapi_resource.foundry.id } },
    { "evals-foundry" = { role = "Foundry User", scope = azapi_resource.foundry.id } },
  )

  scope                = each.value.scope
  role_definition_name = each.value.role
  principal_id         = azurerm_user_assigned_identity.github_deploy.principal_id
  principal_type       = "ServicePrincipal"
}
