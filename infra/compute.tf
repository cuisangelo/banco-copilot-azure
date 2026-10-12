resource "azurerm_container_registry" "main" {
  name                = "${local.flatname}acr"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = false
}

resource "azurerm_container_app_environment" "main" {
  name                       = "${local.name}-env"
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  log_analytics_workspace_id = azurerm_log_analytics_workspace.main.id

  workload_profile {
    name                  = "Consumption"
    workload_profile_type = "Consumption"
  }
}

# Static Web Apps is not offered in canadaeast; the static content is served globally anyway.
resource "azurerm_static_web_app" "web" {
  name                = "${local.name}-web"
  location            = "eastus2"
  resource_group_name = azurerm_resource_group.main.name
  sku_tier            = "Free"
  sku_size            = "Free"
}

resource "azurerm_static_web_app_custom_domain" "web" {
  count             = var.web_custom_domain_enabled ? 1 : 0
  static_web_app_id = azurerm_static_web_app.web.id
  domain_name       = var.web_custom_domain
  validation_type   = "cname-delegation"
}

locals {
  # Placeholder until deploy.yml pushes the real images; Terraform ignores image changes afterwards.
  placeholder_image = "mcr.microsoft.com/k8se/quickstart:latest"
  app_port          = 8000

  app_names     = { for svc in local.services : svc => "${var.prefix}-${svc}" }
  mcp_bank_host = "${local.app_names["mcp-bank"]}.internal.${azurerm_container_app_environment.main.default_domain}"
  cosmos_values = { COSMOS_ENDPOINT = azurerm_cosmosdb_account.main.endpoint, COSMOS_DATABASE = azurerm_cosmosdb_sql_database.copilot.name }

  # env: plain values. secret_env: env var name => Key Vault secret name.
  apps = {
    "products-api" = {
      external   = true
      env        = { PRODUCTS_PATH = "/app/data/products.json" }
      secret_env = { BACKEND_SECRET = "backend-secret" }
    }
    "customers-api" = {
      external = true
      env      = merge(local.cosmos_values, { CUSTOMERS_PATH = "/app/data/customers.json" })
      secret_env = {
        BACKEND_SECRET         = "backend-secret"
        PERSONA_PUBLIC_KEY_PEM = "persona-public-key-pem"
      }
    }
    "mcp-bank" = {
      external = false
      env = {
        APIM_BASE_URL = azurerm_api_management.main.gateway_url
        # FastMCP answers 421 to any Host header not listed here.
        MCP_ALLOWED_HOSTS = local.mcp_bank_host
      }
      secret_env = { APIM_SUBSCRIPTION_KEY = "apim-subscription-key" }
    }
    "copilot-api" = {
      external = true
      env = merge(local.cosmos_values, {
        APIM_BASE_URL                         = azurerm_api_management.main.gateway_url
        AZURE_OPENAI_ENDPOINT                 = local.openai_endpoint
        AZURE_OPENAI_CHAT_DEPLOYMENT          = local.chat_deployment
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT     = local.embed_deployment
        AZURE_OPENAI_API_VERSION              = local.openai_api_version
        SEARCH_ENDPOINT                       = "https://${azurerm_search_service.main.name}.search.windows.net"
        SEARCH_INDEX                          = local.search_index
        CONTENT_SAFETY_ENDPOINT               = azurerm_cognitive_account.content_safety.endpoint
        MCP_BANK_URL                          = "https://${local.mcp_bank_host}/mcp"
        PERSONA_KEY_ID                        = substr(sha256(tls_private_key.persona.public_key_pem), 0, 16)
        DAILY_TOKEN_CAP                       = tostring(var.daily_token_cap)
        CORS_ORIGIN                           = "https://${var.web_custom_domain}"
        APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.main.connection_string
        RETRIEVAL_MODES                       = var.agentic_search_enabled ? "hybrid,agentic" : "hybrid"
        }, var.agentic_search_enabled ? {
        # Answers only once scripts/create_knowledge_base.py has built the knowledge base on it.
        AGENTIC_SEARCH_ENDPOINT = "https://${one(azurerm_search_service.agentic[*].name)}.search.windows.net"
      } : {})
      secret_env = {
        APIM_SUBSCRIPTION_KEY   = "apim-subscription-key"
        PERSONA_PRIVATE_KEY_PEM = "persona-private-key-pem"
      }
    }
  }
}

resource "azurerm_container_app" "app" {
  for_each = local.apps

  name                         = local.app_names[each.key]
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  workload_profile_name        = "Consumption"

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.service[each.key].id]
  }

  registry {
    server   = azurerm_container_registry.main.login_server
    identity = azurerm_user_assigned_identity.service[each.key].id
  }

  dynamic "secret" {
    for_each = toset(values(each.value.secret_env))
    content {
      name                = secret.value
      key_vault_secret_id = azurerm_key_vault_secret.secret[secret.value].versionless_id
      identity            = azurerm_user_assigned_identity.service[each.key].id
    }
  }

  ingress {
    external_enabled = each.value.external
    target_port      = local.app_port
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = 0
    # One replica keeps copilot-api's in-memory per-IP rate limit exact.
    max_replicas = 1

    container {
      name   = each.key
      image  = local.placeholder_image
      cpu    = 0.25
      memory = "0.5Gi"

      # DefaultAzureCredential needs it to pick the user-assigned identity.
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.service[each.key].client_id
      }

      dynamic "env" {
        for_each = each.value.env
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = each.value.secret_env
        content {
          name        = env.key
          secret_name = env.value
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].container[0].image]
  }

  depends_on = [time_sleep.service_rbac]
}
