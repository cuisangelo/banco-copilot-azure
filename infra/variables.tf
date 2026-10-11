variable "prefix" {
  type        = string
  description = "Short lowercase prefix for every resource name."

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,9}$", var.prefix))
    error_message = "prefix must be 3-10 lowercase alphanumerics starting with a letter (it feeds storage and registry names)."
  }
}

variable "location" {
  type        = string
  description = "Single region for the whole deployment (quota and model availability were verified there)."
  default     = "canadaeast"
}

variable "daily_token_cap" {
  type        = number
  description = "Daily Azure OpenAI token cap enforced by copilot-api (DAILY_TOKEN_CAP)."

  validation {
    condition     = var.daily_token_cap > 0
    error_message = "daily_token_cap must be positive."
  }
}

variable "budget_alert_emails" {
  type        = list(string)
  description = "Recipients of the subscription budget alerts; the first one is also the APIM publisher email."

  validation {
    condition     = length(var.budget_alert_emails) > 0
    error_message = "At least one budget alert email is required."
  }
}

variable "github_repository" {
  type        = string
  description = "owner/repo allowed to deploy via OIDC. Null until the remote exists; the deploy identity is created regardless."
  default     = null
}

variable "cosmos_location" {
  type        = string
  description = "Region for Cosmos DB. Kept apart from location because Cosmos refuses new accounts in regions under high demand."
}

variable "web_custom_domain" {
  type        = string
  description = "Public hostname of the web app (e.g. azure.example.com). copilot-api only accepts CORS from it."
}

variable "web_custom_domain_enabled" {
  type        = bool
  description = "Bind web_custom_domain to the Static Web App. Azure validates it against a CNAME to the app's default host, so this is a second apply after creating that DNS record."
  default     = false
}

variable "ingest_trigger_enabled" {
  type        = bool
  description = "Create the Event Grid subscription to the ingest function. Its webhook handshake only succeeds once the function code is deployed, so this is a second apply."
  default     = false
}
