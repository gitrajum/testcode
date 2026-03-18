variable "container_app_mcp_elsa_name" {
  type        = string
  default     = "mcp-elsa"
  description = "Name of the Elsa MCP container app."
}

variable "container_app_mcp_elsa_listening_port" {
  type        = number
  default     = 8000
  description = "Port the Elsa MCP container app listens on."
}

variable "mcp_elsa_cpu" {
  type        = number
  default     = 0.5
  description = "CPU allocation for the Elsa MCP container app."
}

variable "mcp_elsa_memory" {
  type        = string
  default     = "1Gi"
  description = "Memory allocation for the Elsa MCP container app."
}

variable "mcp_elsa_min_replicas" {
  type        = number
  default     = 1
  description = "Minimum number of replicas for the Elsa MCP container app."
}

variable "mcp_elsa_max_replicas" {
  type        = number
  default     = 2
  description = "Maximum number of replicas for the Elsa MCP container app."
}

module "containerapp_mcp_elsa" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/containerapp?ref=v1.0.5"

  container_app_name  = "${var.container_app_name_prefix}-${var.container_app_mcp_elsa_name}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags

  log_analytics_workspace_id   = module.log_analytics_workspace.id
  container_app_environment_id = module.container_app_environment.id
  image_name                   = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" # Placeholder image - real image updated via CI/CD
  container_name               = "mcp-elsa"

  # Registry configuration for ACR with user-assigned identity
  registry_name      = azurerm_container_registry.acr.login_server
  registry_user_name = null
  registry_password  = null
  registry_identity  = azurerm_user_assigned_identity.acr_pull_identity.id

  ingress = {
    target_port = var.container_app_mcp_elsa_listening_port
    # MCP servers are typically called internally by the agent
    external_enabled = false
  }

  # Resource allocation
  cpu    = var.mcp_elsa_cpu
  memory = var.mcp_elsa_memory

  # Horizontal scaling configuration
  replica_limits = {
    min = var.mcp_elsa_min_replicas
    max = var.mcp_elsa_max_replicas
  }

  # User-assigned identity for ACR image pull
  user_assigned_identity_ids = [azurerm_user_assigned_identity.acr_pull_identity.id]

  # Environment variables
  environment_variables = {
    AZURE_TENANT_ID = data.azurerm_client_config.current.tenant_id
    AZURE_CLIENT_ID = var.entraid_application_client_id

    #Databricks configuration
    DATABRICKS_HOST      = "adb-4071335540424391.11.azuredatabricks.net"
    DATABRICKS_HTTP_PATH = "/sql/1.0/warehouses/916c447fdd11cd1e"
    DATABRICKS_CATALOG   = "efdataonelh_prd"
    DATABRICKS_SCHEMA    = "generaldiscovery_servicenow_r"

  }

  secret_environment_variables = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = nonsensitive(module.application_insights.connection_string)
    DATABRICKS_TOKEN                      = var.databricks_token

  }

  depends_on = [
    azurerm_container_registry.acr,
    azurerm_role_assignment.acr_pull_identity_acr_pull,
    module.log_analytics_workspace,
    module.keyvault,
    module.application_insights,
    azurerm_private_endpoint.acr,
    azurerm_private_dns_zone.acr,
    azurerm_private_dns_zone_virtual_network_link.acr,
    module.container_app_environment
  ]
}

# Grant Container App managed identity access to Key Vault secrets
resource "azurerm_role_assignment" "containerapp_mcp_elsa_keyvault" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.containerapp_mcp_elsa.principal_id

  depends_on = [
    module.containerapp_mcp_elsa,
    module.keyvault
  ]
}

resource "azurerm_role_assignment" "containerapp_mcp_elsa_app_insights" {
  scope                = module.application_insights.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = module.containerapp_mcp_elsa.principal_id

  depends_on = [
    module.containerapp_mcp_elsa,
    module.application_insights
  ]
}

output "containerapp_mcp_elsa_url" {
  value       = module.containerapp_mcp_elsa.url
  description = "The URL to access the Elsa MCP container app"
}

output "containerapp_mcp_elsa_name" {
  value       = module.containerapp_mcp_elsa.name
  description = "The name of the Elsa MCP container app"
}

output "containerapp_mcp_elsa_identity_principal_id" {
  value       = module.containerapp_mcp_elsa.principal_id
  description = "The principal ID of the Elsa MCP container app managed identity"
}
