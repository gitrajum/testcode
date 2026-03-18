# Azure OpenAI Service
/*
resource "azurerm_cognitive_account" "aifoundry" {
  name                = "${var.aifoundry_name_prefix}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  kind                = "AIServices"
  sku_name            = "S0"

  custom_subdomain_name = "${var.aifoundry_custom_subdomain}-${local.resource_name_suffix}"

  # Enable project management for AI Foundry
  project_management_enabled = true

  # Network security
  public_network_access_enabled = !var.enable_network_restrictions

  # Network ACLs
  dynamic "network_acls" {
    for_each = var.enable_network_restrictions ? [1] : []
    content {
      default_action = "Deny"

      # Optional: Emergency access IPs
      ip_rules       = var.allowed_ip_ranges

      # Allow Container Apps subnet
      virtual_network_rules {
        subnet_id                            = azurerm_subnet.containerapp.id
        ignore_missing_vnet_service_endpoint = false
      }
    }
  }

  # Managed identity required for project_management_enabled
  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}
*/

# Store OpenAI key in Key Vault
/*
resource "azurerm_key_vault_secret" "azure_aifoundry_key" {
  name         = "azure-aifoundry-key"
  value        = azurerm_cognitive_account.aifoundry.primary_access_key
  key_vault_id = module.keyvault.id

  depends_on = [
    azurerm_cognitive_account.aifoundry,
    module.keyvault,
    azurerm_key_vault_access_policy.terraform_executor
  ]
}
*/

/*
# GPT-5 Model Deployment
resource "azurerm_cognitive_deployment" "gpt5" {
  name                 = "gpt-5-mini"
  cognitive_account_id = azurerm_cognitive_account.aifoundry.id

  model {
    format  = "OpenAI"
    name    = "gpt-5-mini"
    version = "2025-08-07" # Use the latest available version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 250 # 10K TPM (Tokens Per Minute)
  }
}

# GPT-5-mini Model Deployment
resource "azurerm_cognitive_deployment" "gpt5_mini" {
  name                 = "gpt-4o"
  cognitive_account_id = azurerm_cognitive_account.aifoundry.id

  model {
    format  = "OpenAI"
    name    = "gpt-4o"
    version = "2024-08-06" # Use the latest available version
  }

  sku {
    name     = "GlobalStandard"
    capacity = 250 # 10K TPM (Tokens Per Minute)
  }
}

# Output the OpenAI endpoint and keys
output "aifoundry_endpoint" {
  value       = azurerm_cognitive_account.aifoundry.endpoint
  description = "The endpoint URL for the Azure OpenAI service"
}

output "aifoundry_primary_key" {
  value       = azurerm_cognitive_account.aifoundry.primary_access_key
  description = "Primary access key for Azure OpenAI"
  sensitive   = true
}

output "aifoundry_secondary_key" {
  value       = azurerm_cognitive_account.aifoundry.secondary_access_key
  description = "Secondary access key for Azure OpenAI"
  sensitive   = true
}

output "aifoundry_id" {
  value       = azurerm_cognitive_account.aifoundry.id
  description = "The ID of the Azure OpenAI resource"
}

output "aifoundry_custom_subdomain" {
  value       = azurerm_cognitive_account.aifoundry.custom_subdomain_name
  description = "The custom subdomain for the Azure OpenAI service"
}

# Output GPT-5 deployment information
output "gpt5_deployment_name" {
  value       = azurerm_cognitive_deployment.gpt5.name
  description = "The deployment name for GPT-5 model"
}

output "gpt5_deployment_id" {
  value       = azurerm_cognitive_deployment.gpt5.id
  description = "The deployment ID for GPT-5 model"
}

# Output GPT-5-mini deployment information
output "gpt5_mini_deployment_name" {
  value       = azurerm_cognitive_deployment.gpt5_mini.name
  description = "The deployment name for GPT-5-mini model"
}

output "gpt5_mini_deployment_id" {
  value       = azurerm_cognitive_deployment.gpt5_mini.id
  description = "The deployment ID for GPT-5-mini model"
}
*/
