resource "random_id" "id" {
  byte_length = 2
}

data "azurerm_resource_group" "rg" {
  name = "AF_AgentCell_004"
}

data "azurerm_client_config" "current" {}

locals {
  # Single suffix with hyphens for most resources
  resource_name_suffix = "${var.product_name}-${var.env_name}-gwc"


  # Default tags with data-classification, can be overridden by additional_tags
  default_tags = {
    deployed_by         = "terraform"
    context             = "agenticfoundation"
    product             = var.product_name
    environment         = var.stage
    data-classification = "Restricted"
  }

  # Merge default tags with additional tags (additional_tags take precedence)
  tags = merge(local.default_tags, var.additional_tags)
}

# Shared user-assigned managed identity for ACR image pull
# This identity is used by all container apps to pull images from ACR
# Separation of concerns: ACR pull vs runtime access (Key Vault, Cosmos DB, OpenAI)
resource "azurerm_user_assigned_identity" "acr_pull_identity" {
  name                = "mi-acr-pull-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags
}
