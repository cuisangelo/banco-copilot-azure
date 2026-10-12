locals {
  # Python function name in functions/ingest/function_app.py; Event Grid targets it by name.
  ingest_function_name = "ingest_blob"
}

resource "azurerm_service_plan" "ingest" {
  name                = "${local.name}-ingest-plan"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  os_type             = "Linux"
  sku_name            = "FC1"
}

resource "azurerm_function_app_flex_consumption" "ingest" {
  name                = "${local.name}-ingest"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  service_plan_id     = azurerm_service_plan.ingest.id

  runtime_name           = "python"
  runtime_version        = "3.12"
  instance_memory_in_mb  = 2048
  maximum_instance_count = 40

  storage_container_type            = "blobContainer"
  storage_container_endpoint        = "${azurerm_storage_account.main.primary_blob_endpoint}${azurerm_storage_container.ingest_package.name}"
  storage_authentication_type       = "UserAssignedIdentity"
  storage_user_assigned_identity_id = azurerm_user_assigned_identity.service["ingest"].id

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.service["ingest"].id]
  }

  app_settings = {
    AZURE_CLIENT_ID                   = azurerm_user_assigned_identity.service["ingest"].client_id
    AZURE_OPENAI_ENDPOINT             = local.openai_endpoint
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT = local.embed_deployment
    AZURE_OPENAI_API_VERSION          = local.openai_api_version
    SEARCH_ENDPOINT                   = "https://${azurerm_search_service.main.name}.search.windows.net"
    SEARCH_INDEX                      = local.search_index

    # Identity-based host storage.
    AzureWebJobsStorage__accountName = azurerm_storage_account.main.name
    AzureWebJobsStorage__credential  = "managedidentity"
    AzureWebJobsStorage__clientId    = azurerm_user_assigned_identity.service["ingest"].client_id

    # Connection named by the blob trigger in functions/ingest (connection="DocsStorage").
    DocsStorage__blobServiceUri = azurerm_storage_account.main.primary_blob_endpoint
    DocsStorage__credential     = "managedidentity"
    DocsStorage__clientId       = azurerm_user_assigned_identity.service["ingest"].client_id
  }

  site_config {
    application_insights_connection_string = azurerm_application_insights.main.connection_string
  }

  depends_on = [time_sleep.service_rbac]
}

resource "azurerm_eventgrid_system_topic" "storage" {
  name                   = "${local.name}-storage-events"
  location               = azurerm_resource_group.main.location
  resource_group_name    = azurerm_resource_group.main.name
  source_arm_resource_id = azurerm_storage_account.main.id
  topic_type             = "Microsoft.Storage.StorageAccounts"
}

data "azurerm_function_app_host_keys" "ingest" {
  count = var.ingest_trigger_enabled ? 1 : 0

  name                = azurerm_function_app_flex_consumption.ingest.name
  resource_group_name = azurerm_resource_group.main.name
}

resource "azurerm_eventgrid_system_topic_event_subscription" "docs" {
  count = var.ingest_trigger_enabled ? 1 : 0

  name                 = "docs-to-ingest"
  system_topic         = azurerm_eventgrid_system_topic.storage.name
  resource_group_name  = azurerm_resource_group.main.name
  included_event_types = ["Microsoft.Storage.BlobCreated"]

  subject_filter {
    subject_begins_with = "/blobServices/default/containers/${azurerm_storage_container.docs.name}/"
  }

  webhook_endpoint {
    url                               = "https://${azurerm_function_app_flex_consumption.ingest.default_hostname}/runtime/webhooks/blobs?functionName=Host.Functions.${local.ingest_function_name}&code=${data.azurerm_function_app_host_keys.ingest[0].blobs_extension_key}"
    max_events_per_batch              = 1
    preferred_batch_size_in_kilobytes = 64
  }
}
