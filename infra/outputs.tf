output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "container_app_names" {
  value = local.app_names
}

output "copilot_api_url" {
  value = "https://${azurerm_container_app.app["copilot-api"].ingress[0].fqdn}"
}

output "apim_gateway_url" {
  value = azurerm_api_management.main.gateway_url
}

output "web_url" {
  value = "https://${azurerm_static_web_app.web.default_host_name}"
}

output "static_web_app_deployment_token" {
  value     = azurerm_static_web_app.web.api_key
  sensitive = true
}

output "ingest_function_name" {
  value = azurerm_function_app_flex_consumption.ingest.name
}

output "docs_storage_account" {
  value = azurerm_storage_account.main.name
}

output "openai_endpoint" {
  value = local.openai_endpoint
}

output "search_endpoint" {
  value = "https://${azurerm_search_service.main.name}.search.windows.net"
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

# GitHub repository variables for deploy.yml.
output "github_deploy" {
  value = {
    AZURE_CLIENT_ID       = azurerm_user_assigned_identity.github_deploy.client_id
    AZURE_TENANT_ID       = data.azurerm_client_config.current.tenant_id
    AZURE_SUBSCRIPTION_ID = data.azurerm_client_config.current.subscription_id
    AZURE_RESOURCE_GROUP  = azurerm_resource_group.main.name
    ACR_NAME              = azurerm_container_registry.main.name
    APP_NAME_PREFIX       = var.prefix
    INGEST_FUNCTION_NAME  = azurerm_function_app_flex_consumption.ingest.name
  }
}
