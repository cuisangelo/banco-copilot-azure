terraform {
  required_version = ">= 1.9"

  backend "local" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}

# Both providers read the subscription from ARM_SUBSCRIPTION_ID and fail without it.
provider "azurerm" {
  # The storage account has shared keys disabled.
  storage_use_azuread = true

  features {
    key_vault {
      purge_soft_delete_on_destroy = true
    }
    cognitive_account {
      purge_soft_delete_on_destroy = true
    }
  }
}

provider "azapi" {}
