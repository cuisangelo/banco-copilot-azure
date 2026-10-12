# Offline plan-time checks of the security and FinOps invariants in the spec (§5, §6, §10).
# Run: terraform -chdir=infra test

mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id       = "00000000-0000-0000-0000-000000000001"
      object_id       = "00000000-0000-0000-0000-000000000002"
      subscription_id = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_data "azurerm_subscription" {
    defaults = {
      id              = "/subscriptions/00000000-0000-0000-0000-000000000003"
      subscription_id = "00000000-0000-0000-0000-000000000003"
    }
  }
}

mock_provider "azapi" {}

variables {
  prefix                  = "bctest"
  daily_token_cap         = 1000
  budget_alert_emails     = ["owner@example.com"]
  web_custom_domain       = "copilot.example.com"
  cosmos_location         = "canadacentral"
  content_safety_location = "eastus2"
}

run "every_required_env_var_from_the_contracts_is_set" {
  command = plan

  assert {
    condition = alltrue([
      for app, names in {
        "products-api"  = ["BACKEND_SECRET", "PRODUCTS_PATH"]
        "customers-api" = ["BACKEND_SECRET", "CUSTOMERS_PATH", "PERSONA_PUBLIC_KEY_PEM", "COSMOS_ENDPOINT", "COSMOS_DATABASE"]
        "mcp-bank"      = ["APIM_BASE_URL", "APIM_SUBSCRIPTION_KEY", "MCP_ALLOWED_HOSTS"]
        "copilot-api" = [
          "APIM_BASE_URL", "APIM_SUBSCRIPTION_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_CHAT_DEPLOYMENT",
          "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "AZURE_OPENAI_API_VERSION", "SEARCH_ENDPOINT", "SEARCH_INDEX",
          "CONTENT_SAFETY_ENDPOINT", "COSMOS_ENDPOINT", "COSMOS_DATABASE", "MCP_BANK_URL", "PERSONA_PRIVATE_KEY_PEM",
          "PERSONA_KEY_ID", "DAILY_TOKEN_CAP", "CORS_ORIGIN", "APPLICATIONINSIGHTS_CONNECTION_STRING", "RETRIEVAL_MODES",
        ]
      } : length(setsubtract(names, azurerm_container_app.app[app].template[0].container[0].env[*].name)) == 0
    ])
    error_message = "A container app is missing an environment variable required by the contracts."
  }

  assert {
    condition = length(setsubtract(
      ["AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "AZURE_OPENAI_API_VERSION", "SEARCH_ENDPOINT", "SEARCH_INDEX"],
      keys(azurerm_function_app_flex_consumption.ingest.app_settings),
    )) == 0
    error_message = "The ingest function is missing an app setting required by the contracts."
  }
}

run "credentials_reach_apps_only_as_key_vault_references" {
  command = plan

  assert {
    condition = alltrue(flatten([
      for app in azurerm_container_app.app : [
        for e in app.template[0].container[0].env : e.secret_name != null && e.value == null
        if contains(["BACKEND_SECRET", "APIM_SUBSCRIPTION_KEY", "PERSONA_PRIVATE_KEY_PEM", "PERSONA_PUBLIC_KEY_PEM"], e.name)
      ]
    ]))
    error_message = "A credential reaches a container app as a plain environment value instead of a Key Vault secret reference."
  }

  assert {
    condition = alltrue(flatten([
      for app in azurerm_container_app.app : [for s in app.secret : s.value == null]
    ]))
    error_message = "A container app secret holds an inline value instead of a Key Vault reference."
  }

  assert {
    condition     = azurerm_key_vault.main.rbac_authorization_enabled
    error_message = "Key Vault must use RBAC so access is granted per identity and per secret."
  }
}

run "only_copilot_and_backends_are_reachable_from_outside" {
  command = plan

  assert {
    condition     = azurerm_container_app.app["mcp-bank"].ingress[0].external_enabled == false
    error_message = "mcp-bank must have internal ingress only."
  }

  assert {
    condition = alltrue([
      for app in ["copilot-api", "products-api", "customers-api"] : azurerm_container_app.app[app].ingress[0].external_enabled
    ])
    error_message = "copilot-api and the APIM backends need external ingress."
  }

  assert {
    condition     = alltrue([for app in azurerm_container_app.app : app.template[0].min_replicas == 0])
    error_message = "Every container app must scale to zero."
  }
}

run "state_store_matches_the_contracts_and_stays_free" {
  command = plan

  assert {
    condition     = azurerm_cosmosdb_account.main.free_tier_enabled && !azurerm_cosmosdb_account.main.local_authentication_enabled
    error_message = "Cosmos must be free tier with key auth disabled."
  }

  assert {
    condition = {
      for name, c in azurerm_cosmosdb_sql_container.container : name => c.partition_key_paths[0]
      } == {
      sessions        = "/session_id"
      checkpoints     = "/session_id"
      access_requests = "/customer_id"
      grants          = "/customer_id"
      audit           = "/actor"
      usage           = "/day"
    }
    error_message = "Cosmos containers or partition keys diverge from the contracts."
  }

  assert {
    condition     = azurerm_cosmosdb_sql_container.container["grants"].default_ttl == -1
    error_message = "grants needs TTL enabled without a default so each grant expires at its own expires_at."
  }

  assert {
    condition     = azurerm_search_service.main.sku == "free"
    error_message = "AI Search must stay on the free SKU."
  }

  assert {
    condition     = length(azurerm_search_service.agentic) == 0
    error_message = "The billed Basic search service for agentic retrieval exists only when agentic_search_enabled is set."
  }
}

run "agentic_mode_gets_a_basic_search_reachable_only_with_identities" {
  command = plan

  variables {
    agentic_search_enabled = true
  }

  assert {
    condition     = azurerm_search_service.agentic[0].sku == "basic" && !azurerm_search_service.agentic[0].local_authentication_enabled
    error_message = "Agentic retrieval needs a Basic search service with key auth disabled."
  }

  assert {
    condition = (
      azurerm_role_assignment.service["copilot-api/agentic-search"].role_definition_name == "Search Index Data Reader" &&
      azurerm_role_assignment.service["agentic-search/openai"].role_definition_name == "Cognitive Services OpenAI User"
    )
    error_message = "copilot-api must read the agentic index and the search service must call the planner model with identities."
  }

  assert {
    condition = [
      for env in azurerm_container_app.app["copilot-api"].template[0].container[0].env : env.value
      if env.name == "RETRIEVAL_MODES"
    ] == ["hybrid,agentic"]
    error_message = "copilot-api must offer the agentic mode when its search service exists."
  }
}

run "budget_alerts_at_50_and_100_usd" {
  command = plan

  assert {
    condition = toset([
      for n in azurerm_consumption_budget_subscription.main.notification : azurerm_consumption_budget_subscription.main.amount * n.threshold / 100
    ]) == toset([50, 100])
    error_message = "Budget alerts must fire at USD 50 and USD 100."
  }
}

run "oidc_repository_rejects_the_plain_owner_repo_form" {
  command = plan

  variables {
    github_repository = "owner/repo"
  }

  expect_failures = [var.github_repository]
}

run "oidc_subjects_use_github_immutable_ids" {
  command = plan

  variables {
    github_repository = "owner@1/repo@2"
  }

  assert {
    condition     = azurerm_federated_identity_credential.github_main[0].subject == "repo:owner@1/repo@2:ref:refs/heads/main"
    error_message = "The main-branch subject must use GitHub's immutable-id form."
  }

  assert {
    condition     = azurerm_federated_identity_credential.github_pull_request[0].subject == "repo:owner@1/repo@2:pull_request"
    error_message = "The pull-request subject must use GitHub's immutable-id form."
  }
}
