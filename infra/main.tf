data "azurerm_client_config" "current" {}

data "azurerm_subscription" "current" {}

resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

locals {
  # Globally unique names (Key Vault, storage, registry, Cosmos, Search, APIM, AI accounts) need a suffix.
  name     = "${var.prefix}-${random_string.suffix.result}"
  flatname = "${var.prefix}${random_string.suffix.result}"

  services = toset(["copilot-api", "mcp-bank", "products-api", "customers-api"])
}

resource "azurerm_resource_group" "main" {
  name     = "${var.prefix}-rg"
  location = var.location
}
