# Storage Account Outputs
output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.agent_storage.name
}

output "storage_account_id" {
  description = "ID of the storage account"
  value       = azurerm_storage_account.agent_storage.id
}

output "storage_connection_string" {
  description = "Connection string for the storage account"
  value       = azurerm_storage_account.agent_storage.primary_connection_string
  sensitive   = true
}
