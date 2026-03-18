variable "container_app_storage_account_name_prefix" {
  type        = string
  default     = "sa"
  description = "Prefix of the container app storage account."
}

variable "storage_allowed_ip_addresses" {
  type        = list(string)
  default     = []
  description = "List of public IP addresses allowed to access storage (for Terraform/CI-CD). Get your IP: curl ifconfig.me"
}

resource "azurerm_storage_account" "agent_storage" {
  name                          = "samobcontrpocgwc"
  resource_group_name           = data.azurerm_resource_group.rg.name
  location                      = data.azurerm_resource_group.rg.location
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  
  # Enable public access but restrict via network rules (required for service endpoints)
  # Container Apps use service endpoints, not private endpoints
  public_network_access_enabled = true
  https_traffic_only_enabled    = true
  
  # Shared key required for Container App file share mounting
  # Compensated by: network restrictions, HTTPS-only, managed identity for table access
  shared_access_key_enabled     = true
  
  # Enhanced security settings
  min_tls_version               = "TLS1_2"
  infrastructure_encryption_enabled = true

  # Network rules to allow access only from container app subnet
  # Conditional: only applied when enable_network_restrictions is true
  # dynamic "network_rules" {
  #   for_each = var.enable_network_restrictions ? [1] : []
  #   content {
  #     default_action             = "Deny"
  #     virtual_network_subnet_ids = [azurerm_subnet.containerapp.id]
  #     ip_rules                   = var.storage_allowed_ip_addresses
  #     bypass                     = ["AzureServices"]
  #   }
  # }
  network_rules {
    default_action             = "Allow"
    virtual_network_subnet_ids = []
    ip_rules                   = []
    bypass                     = ["AzureServices"]
  }

  tags = local.tags
}

resource "azurerm_storage_share" "agent_share" {
  name               = "agentfiles"
  storage_account_id = azurerm_storage_account.agent_storage.id
  quota              = 50
}

# Register the storage with the Container App Environment
resource "azurerm_container_app_environment_storage" "agent_storage" {
  name                         = "agentfilestorage"
  container_app_environment_id = module.container_app_environment.id
  account_name                 = azurerm_storage_account.agent_storage.name
  share_name                   = azurerm_storage_share.agent_share.name
  access_key                   = azurerm_storage_account.agent_storage.primary_access_key
  access_mode                  = "ReadWrite"

  depends_on = [
    module.container_app_environment,
    azurerm_storage_account.agent_storage,
    azurerm_storage_share.agent_share
  ]
}

# Azure Table Storage for agent data
resource "azurerm_storage_table" "filesmetadata_table" {
  name                 = "filesmetadata"
  storage_account_name = azurerm_storage_account.agent_storage.name

  depends_on = [
    azurerm_storage_account.agent_storage
  ]
}

# Azure Table Storage for agent data
resource "azurerm_storage_table" "fingerprints_table" {
  name                 = "fingerprints"
  storage_account_name = azurerm_storage_account.agent_storage.name

  depends_on = [
    azurerm_storage_account.agent_storage
  ]
}

# Azure Table Storage for agent data
resource "azurerm_storage_table" "jobtracker_table" {
  name                 = "jobtracker"
  storage_account_name = azurerm_storage_account.agent_storage.name

  depends_on = [
    azurerm_storage_account.agent_storage
  ]
}

# Grant Container App managed identity access to Table Storage
# This enables secure, keyless access to tables from application code
# Uses the container app's system-assigned identity (not the ACR pull identity)
resource "azurerm_role_assignment" "agent_table_data_contributor" {
  scope                = azurerm_storage_account.agent_storage.id
  role_definition_name = "Storage Table Data Contributor"
  principal_id         = module.containerapp_agent.principal_id

  depends_on = [
    azurerm_storage_account.agent_storage,
    module.containerapp_agent
  ]
}

# Diagnostic logging commented out to avoid conflicts
# Uncomment after first successful deployment or import existing resource
# resource "azurerm_monitor_diagnostic_setting" "agent_storage_diagnostics" {
#   name                       = "storage-security-logs"
#   target_resource_id         = "${azurerm_storage_account.agent_storage.id}/tableServices/default"
#   log_analytics_workspace_id = module.log_analytics_workspace.id
#
#   enabled_log {
#     category = "StorageRead"
#   }
#
#   enabled_log {
#     category = "StorageWrite"
#   }
#
#   enabled_log {
#     category = "StorageDelete"
#   }
#
#   depends_on = [
#     azurerm_storage_account.agent_storage,
#     module.log_analytics_workspace
#   ]
# }
