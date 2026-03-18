module "keyvault" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/keyvault?ref=v1.0.7"

  # Use abbreviated suffix to stay within 24-character limit for Key Vault names
  key_vault_name      = "${var.keyvault_name_prefix}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name

  enable_rbac_authorization = true

  # Soft delete and purge protection for enhanced security
  soft_delete_retention_days = 90
  purge_protection_enabled   = true

  tags = local.tags
}

variable "developer_object_id" {
  description = "Object ID of the developer for local testing access"
  type        = string
  default     = null
}

# Grant the current Terraform executing identity access to Key Vault using RBAC
# CRITICAL: This must be unconditional because Terraform needs access to manage
# secrets, keys, and certificates. Without this, you get 403 errors.
# In GitHub Actions: current.object_id = GitHub Actions SP
# In local dev: current.object_id = developer's identity
resource "azurerm_role_assignment" "terraform_executor_kv_admin" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = data.azurerm_client_config.current.object_id

  depends_on = [module.keyvault]
}

# Grant developer access to Key Vault for local testing using RBAC
resource "azurerm_role_assignment" "developer_kv_admin" {
  count                = var.developer_object_id != null && var.developer_object_id != "" ? 1 : 0
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Administrator"
  principal_id         = var.developer_object_id

  depends_on = [module.keyvault]
}

# Outputs
output "keyvault_name" {
  description = "The name of the Key Vault."
  value       = module.keyvault.name
}
output "keyvault_vault_uri" {
  description = "The URI of the Key Vault."
  value       = module.keyvault.vault_uri
}
