locals {
  foundry_subdomain  = "${local.name}-foundry"
  openai_endpoint    = "https://${local.foundry_subdomain}.openai.azure.com/"
  openai_api_version = "2024-10-21"
  chat_deployment    = "gpt-4.1-mini"
  embed_deployment   = "text-embedding-3-small"
}

resource "azapi_resource" "foundry" {
  type      = "Microsoft.CognitiveServices/accounts@2025-06-01"
  name      = "${local.name}-foundry"
  parent_id = azurerm_resource_group.main.id
  location  = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  body = {
    kind = "AIServices"
    sku  = { name = "S0" }
    properties = {
      allowProjectManagement = true
      customSubDomainName    = local.foundry_subdomain
      disableLocalAuth       = true
      publicNetworkAccess    = "Enabled"
    }
  }
}

resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = "${var.prefix}-project"
  parent_id = azapi_resource.foundry.id
  location  = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  body = {
    properties = {
      displayName = "Banco Copilot"
      description = "Copiloto cognitivo para asesores de Banco Austral (demo)."
    }
  }
}

resource "azapi_resource" "chat_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = local.chat_deployment
  parent_id = azapi_resource.foundry.id

  body = {
    sku = { name = "GlobalStandard", capacity = 200 }
    properties = {
      model = { format = "OpenAI", name = "gpt-4.1-mini", version = "2025-04-14" }
    }
  }
}

resource "azapi_resource" "embedding_deployment" {
  type      = "Microsoft.CognitiveServices/accounts/deployments@2025-06-01"
  name      = local.embed_deployment
  parent_id = azapi_resource.foundry.id

  body = {
    sku = { name = "GlobalStandard", capacity = 100 }
    properties = {
      model = { format = "OpenAI", name = "text-embedding-3-small", version = "1" }
    }
  }

  # The account rejects concurrent deployment operations.
  depends_on = [azapi_resource.chat_deployment]
}

resource "azurerm_cognitive_account" "content_safety" {
  name                  = "${local.name}-safety-${var.content_safety_location}"
  location              = var.content_safety_location
  resource_group_name   = azurerm_resource_group.main.name
  kind                  = "ContentSafety"
  sku_name              = "S0"
  custom_subdomain_name = "${local.name}-safety-${var.content_safety_location}"
  local_auth_enabled    = false
}
