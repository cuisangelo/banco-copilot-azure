locals {
  search_index = "bank-docs"
}

# The bank-docs index itself is created by functions/ingest (index_schema.py), not here.
resource "azurerm_search_service" "main" {
  name                         = "${local.name}-search"
  location                     = azurerm_resource_group.main.location
  resource_group_name          = azurerm_resource_group.main.name
  sku                          = "free"
  semantic_search_sku          = "free"
  local_authentication_enabled = false
}
