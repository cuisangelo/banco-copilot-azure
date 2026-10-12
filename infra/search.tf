locals {
  search_index = "bank-docs"
}

# The bank-docs index itself is created by functions/ingest (index_schema.py), not here.
resource "azurerm_search_service" "main" {
  name                         = "${local.name}-search"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  sku                          = "free"
  local_authentication_enabled = false

  # Semantic ranking is owned by azapi_update_resource.search_semantic below.
  lifecycle {
    ignore_changes = [semantic_search_sku]
  }
}

# copilot-api queries with semantic reranking. Azure accepts the free semantic plan on the free
# tier, but the azurerm provider rejects semantic_search_sku there, so it is set through ARM.
resource "azapi_update_resource" "search_semantic" {
  type        = "Microsoft.Search/searchServices@2025-05-01"
  resource_id = azurerm_search_service.main.id
  body = {
    properties = {
      semanticSearch = "free"
    }
  }
}

# Agentic retrieval plans its subqueries with the chat model, which it calls as the search
# service's managed identity; the free tier cannot. So it gets its own Basic service, up only for
# demos, with the same bank-docs index loaded by scripts/ingest_local.py.
resource "azurerm_search_service" "agentic" {
  count = var.agentic_search_enabled ? 1 : 0

  name                         = "${local.name}-agentic-search"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  sku                          = "basic"
  local_authentication_enabled = false
  semantic_search_sku          = "free"

  identity {
    type = "SystemAssigned"
  }
}
