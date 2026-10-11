resource "azurerm_cosmosdb_account" "main" {
  name                         = "${local.name}-cosmos"
  location                     = var.cosmos_location
  resource_group_name          = azurerm_resource_group.main.name
  offer_type                   = "Standard"
  kind                         = "GlobalDocumentDB"
  free_tier_enabled            = true
  local_authentication_enabled = false

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.cosmos_location
    failover_priority = 0
  }
}

# Shared database throughput keeps all containers inside the 1000 RU/s free tier.
resource "azurerm_cosmosdb_sql_database" "copilot" {
  name                = "copilot"
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  throughput          = 1000
}

resource "azurerm_cosmosdb_sql_container" "container" {
  for_each = {
    sessions        = "/session_id"
    checkpoints     = "/session_id"
    access_requests = "/customer_id"
    grants          = "/customer_id"
    audit           = "/actor"
    usage           = "/day"
  }

  name                = each.key
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  database_name       = azurerm_cosmosdb_sql_database.copilot.name
  partition_key_paths = [each.value]

  # -1 enables TTL with no default: each grant document carries its own ttl up to expires_at.
  default_ttl = each.key == "grants" ? -1 : null
}

resource "azurerm_storage_account" "main" {
  name                            = "${local.flatname}st"
  location                        = azurerm_resource_group.main.location
  resource_group_name             = azurerm_resource_group.main.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  account_kind                    = "StorageV2"
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  min_tls_version                 = "TLS1_2"
}

resource "azurerm_storage_container" "docs" {
  name               = "docs"
  storage_account_id = azurerm_storage_account.main.id
}

resource "azurerm_storage_container" "ingest_package" {
  name               = "ingest-package"
  storage_account_id = azurerm_storage_account.main.id
}
