resource "azurerm_api_management" "main" {
  name                = "${local.name}-apim"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  publisher_name      = "Banco Austral (demo)"
  publisher_email     = var.budget_alert_emails[0]
  sku_name            = "Consumption_0"

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_api_management_named_value" "backend_secret" {
  name                = "backend-secret"
  display_name        = "backend-secret"
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name
  secret              = true

  value_from_key_vault {
    secret_id = azurerm_key_vault_secret.secret["backend-secret"].versionless_id
  }

  depends_on = [time_sleep.service_rbac]
}

locals {
  apis = {
    products = {
      path    = "products-api"
      backend = "products-api"
      operations = {
        "list-products" = { method = "GET", url = "/products", params = [] }
        "get-product"   = { method = "GET", url = "/products/{id}", params = ["id"] }
      }
    }
    customers = {
      path    = "customers-api"
      backend = "customers-api"
      operations = {
        "get-customer-profile" = { method = "GET", url = "/customers/{id}/profile", params = ["id"] }
        "get-customer-fields"  = { method = "POST", url = "/customers/{id}/fields", params = ["id"] }
        "create-grant"         = { method = "POST", url = "/grants", params = [] }
      }
    }
  }

  api_operations = merge([
    for api, cfg in local.apis : {
      for op, o in cfg.operations : "${api}/${op}" => merge(o, { api = api, name = op })
    }
  ]...)
}

resource "azurerm_api_management_api" "api" {
  for_each = local.apis

  name                  = each.key
  display_name          = each.key
  path                  = each.value.path
  protocols             = ["https"]
  revision              = "1"
  api_management_name   = azurerm_api_management.main.name
  resource_group_name   = azurerm_resource_group.main.name
  service_url           = "https://${azurerm_container_app.app[each.value.backend].ingress[0].fqdn}"
  subscription_required = true
}

resource "azurerm_api_management_api_operation" "op" {
  for_each = local.api_operations

  operation_id        = each.value.name
  api_name            = azurerm_api_management_api.api[each.value.api].name
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name
  display_name        = each.value.name
  method              = each.value.method
  url_template        = each.value.url

  dynamic "template_parameter" {
    for_each = toset(each.value.params)
    content {
      name     = template_parameter.value
      type     = "string"
      required = true
    }
  }
}

# Consumption has no rate-limit-by-key, so the limit is per subscription (the only caller is mcp-bank/copilot-api).
resource "azurerm_api_management_api_policy" "api" {
  for_each = local.apis

  api_name            = azurerm_api_management_api.api[each.key].name
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name

  xml_content = <<-XML
    <policies>
      <inbound>
        <base />
        <rate-limit calls="120" renewal-period="60" />
        <set-header name="X-Backend-Secret" exists-action="override">
          <value>{{${azurerm_api_management_named_value.backend_secret.display_name}}}</value>
        </set-header>
      </inbound>
      <backend>
        <base />
      </backend>
      <outbound>
        <base />
      </outbound>
      <on-error>
        <base />
      </on-error>
    </policies>
  XML
}

resource "azurerm_api_management_product" "bank" {
  product_id            = "bank-apis"
  display_name          = "Bank APIs"
  api_management_name   = azurerm_api_management.main.name
  resource_group_name   = azurerm_resource_group.main.name
  subscription_required = true
  approval_required     = false
  published             = true
}

resource "azurerm_api_management_product_api" "bank" {
  for_each = local.apis

  product_id          = azurerm_api_management_product.bank.product_id
  api_name            = azurerm_api_management_api.api[each.key].name
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_api_management_subscription" "mcp_bank" {
  display_name        = "mcp-bank"
  api_management_name = azurerm_api_management.main.name
  resource_group_name = azurerm_resource_group.main.name
  product_id          = azurerm_api_management_product.bank.id
  state               = "active"
}
