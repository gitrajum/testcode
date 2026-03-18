terraform {
  required_providers {
    azurerm = {
      version = ">=3.63.0"
      source  = "hashicorp/azurerm"
    }
    random = {
      version = ">=3.5.0"
      source  = "hashicorp/random"
    }
  }
  required_version = ">=1.5.5"
  backend "azurerm" {
    resource_group_name  = "AF_AgentCell_004"
    storage_account_name = "agentcell004states"
    container_name       = "tfstate"
    key                  = "poc.tfstate"
  }
}

provider "azurerm" {
  subscription_id = var.subscription_id
  resource_providers_to_register = [
    "Microsoft.Communication",
    "Microsoft.App",
    "Microsoft.OperationalInsights"
  ]

  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}
