resource "azurerm_log_analytics_workspace" "main" {
  name                = "${local.name}-logs"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "PerGB2018"
  retention_in_days   = 30
}

resource "azurerm_application_insights" "main" {
  name                = "${local.name}-appi"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  workspace_id        = azurerm_log_analytics_workspace.main.id
  application_type    = "web"
}

# Foundry Tracing reads the project's traces from this App Insights connection.
resource "azapi_resource" "foundry_appinsights" {
  type      = "Microsoft.CognitiveServices/accounts/projects/connections@2025-06-01"
  name      = "appinsights"
  parent_id = azapi_resource.foundry_project.id

  body = {
    properties = {
      category      = "AppInsights"
      target        = azurerm_application_insights.main.id
      authType      = "ApiKey"
      isSharedToAll = true
      credentials   = { key = azurerm_application_insights.main.connection_string }
      metadata      = { ApiType = "Azure", ResourceId = azurerm_application_insights.main.id }
    }
  }
}

locals {
  # Span attributes emitted by copilot-api (spec §7). gen_ai.* follow the OTel GenAI conventions.
  workbook_queries = {
    "Tokens por día"                                     = <<-KQL
      dependencies
      | where isnotempty(customDimensions["gen_ai.usage.input_tokens"])
      | summarize entrada = sum(toint(customDimensions["gen_ai.usage.input_tokens"])), salida = sum(toint(customDimensions["gen_ai.usage.output_tokens"])) by bin(timestamp, 1d)
      | render columnchart
    KQL
    "Latencia de /chat (p50 / p95)"                      = <<-KQL
      requests
      | where name has "/chat"
      | summarize p50 = percentile(duration, 50), p95 = percentile(duration, 95) by bin(timestamp, 1h)
      | render timechart
    KQL
    "Costo estimado por invocación (USD)"                = <<-KQL
      dependencies
      | where isnotempty(customDimensions["cost_usd_estimate"])
      | summarize costo = sum(todouble(customDimensions["cost_usd_estimate"])) by operation_Id, bin(timestamp, 1d)
      | summarize promedio = avg(costo), p95 = percentile(costo, 95), total = sum(costo) by timestamp
      | render timechart
    KQL
    "Rechazos por guardrail"                             = <<-KQL
      dependencies
      | where isnotempty(customDimensions["guardrail.layer"])
      | summarize rechazos = count() by capa = tostring(customDimensions["guardrail.layer"]), bin(timestamp, 1d)
      | render columnchart
    KQL
    "Decisiones de autorización y solicitudes de acceso" = <<-KQL
      dependencies
      | where isnotempty(customDimensions["authz.decision"]) or isnotempty(customDimensions["access_request.status"])
      | extend evento = coalesce(tostring(customDimensions["access_request.status"]), tostring(customDimensions["authz.decision"]))
      | summarize total = count() by evento, bin(timestamp, 1d)
      | render columnchart
    KQL
  }
}

resource "random_uuid" "workbook" {}

resource "azurerm_application_insights_workbook" "copilot" {
  name                = random_uuid.workbook.result
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  display_name        = "Banco Copilot — operación y costos"
  source_id           = lower(azurerm_application_insights.main.id)

  data_json = jsonencode({
    version = "Notebook/1.0"
    items = [
      for title, query in local.workbook_queries : {
        type = 3
        name = title
        content = {
          version       = "KqlItem/1.0"
          title         = title
          query         = query
          timeContext   = { durationMs = 2592000000 }
          queryType     = 0
          resourceType  = "microsoft.insights/components"
          visualization = strcontains(query, "timechart") ? "timechart" : "barchart"
        }
      }
    ]
  })
}
