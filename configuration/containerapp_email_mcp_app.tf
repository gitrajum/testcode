# variable "container_app_email_mcp_app_environment_name_prefix" {
#   #default     = "cae-emailmcp"
#   description = "Prefix of the container app environment."
# }

variable "container_app_email_mcp_app_name" {
  type        = string
  default     = "emailmcp"
  description = "Name of the Email MCP container app."
}

variable "email_from_domain" {
  type        = string
  description = "Email domain for sending emails. Use 'agent.bayer.com' for custom domain or Azure managed domain GUID"
  default     = "agent.bayer.com"
}

variable "emailmcp_otel_enabled" {
  type        = bool
  default     = false
  description = "Enable OpenTelemetry for Email MCP"
}

variable "emailmcp_otel_service_name" {
  type        = string
  default     = "email-mcp"
  description = "Service name for OpenTelemetry tracing"
}

variable "emailmcp_otel_exporter_endpoint" {
  type        = string
  default     = "http://localhost:4318"
  description = "OpenTelemetry exporter OTLP endpoint"
}

variable "emailmcp_mi_client_id" {
  type        = string
  description = "App registration client id"
  default     = ""
}

variable "container_app_email_mcp_listening_port" {
  type        = number
  default     = 8000
  description = "Port the Email MCP container app listens on."
}

module "containerapp-email-mcp-app" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/containerapp?ref=v1.0.5"

  # Use abbreviated suffix to stay within 32-character limit
  container_app_name  = "${var.container_app_name_prefix}-${var.container_app_email_mcp_app_name}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags

  log_analytics_workspace_id = module.log_analytics_workspace.id

  # Use the same Container Apps Environment as the agent for secure internal communication
  container_app_environment_id = module.container_app_environment.id

  # Using Microsoft's public Container Apps hello-world image as placeholder (no ACR auth needed)
  # Real email-mcp image from ACR will be updated via CI/CD
  image_name     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest"
  container_name = "email-mcp-app"

  # Registry configuration for ACR with user-assigned identity
  # Set to null for public images, will be updated by CI/CD when deploying from ACR
  registry_name      = null
  registry_user_name = null
  registry_password  = null
  registry_identity  = null

  ingress = {
    target_port = 80 # Placeholder nginx uses port 80, will be updated to 8000 by CI/CD for real email-mcp image
  }

  # Resource allocation
  cpu    = 1
  memory = "2Gi"

  # Horizontal scaling configuration
  replica_limits = {
    min = 1
    max = 1
  }

  # User-assigned identity for ACR image pull (commented out for initial deployment with public image)
  # CI/CD will configure ACR registry and identity when deploying real email-mcp image
  # user_assigned_identity_ids = [azurerm_user_assigned_identity.acr_pull_identity.id]
  user_assigned_identity_ids = []

  # IP restrictions to allow only specific IP for external access
  # Internal traffic from containerapp_agent bypasses these restrictions automatically
  # Temporarily disabled to troubleshoot provisioning timeout
  ip_restrictions = null

  # ip_restrictions = {
  #   action = "Allow"
  #   rules = [
  #     {
  #       name             = "allow-your-ip"
  #       description      = "Allow access from your specific IP address"
  #       ip_address_range = "212.64.228.99/32"
  #     },
  #     {
  #       name             = "allow-secondary-ip"
  #       description      = "Allow access from secondary IP address"
  #       ip_address_range = "212.64.228.98/32"
  #     }
  #   ]
  # }

  # Environment variables
  environment_variables = {
    MCP_SERVER_HOST            = "0.0.0.0"
    MCP_SERVER_PORT            = var.container_app_email_mcp_listening_port
    LOG_LEVEL                  = "INFO"
    LOG_FORMAT                 = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    MCP_AUTH_ENABLED           = "true"
    AZURE_TENANT_ID            = data.azurerm_client_config.current.tenant_id
    MANAGED_IDENTITY_CLIENT_ID = var.emailmcp_mi_client_id
    AUTH_RESOURCE_SERVER_URL   = "https://login.microsoftonline.com/${data.azurerm_client_config.current.tenant_id}/v2.0"
    AUTH_CLIENT_ID             = var.emailmcp_mi_client_id
    AUTH_AUDIENCE              = "api://${var.emailmcp_mi_client_id}"
    AZURE_EMAIL_DOMAIN         = var.email_from_domain

    # Telemetry Configuration
    OTEL_ENABLED                = tostring(var.emailmcp_otel_enabled)
    OTEL_SERVICE_NAME           = var.emailmcp_otel_service_name
    OTEL_EXPORTER_OTLP_ENDPOINT = var.emailmcp_otel_exporter_endpoint
  }

  # Secrets from Key Vault
  secret_environment_variables = {}

  depends_on = [
    azurerm_container_registry.acr,
    azurerm_role_assignment.acr_pull_identity_acr_pull,
    module.log_analytics_workspace,
    module.keyvault,
    module.container_app_environment,
    azurerm_communication_service.communication
  ]
}

output "containerapp_email_mcp_app_url" {
  value       = module.containerapp-email-mcp-app.url
  description = "The URL to access the container app"
}

output "containerapp_email_mcp_app_name" {
  value       = module.containerapp-email-mcp-app.name
  description = "The name of the container app"
}


# Grant Container App managed identity access to Key Vault secrets
resource "azurerm_role_assignment" "containerapp-email-mcp-app_keyvault" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.containerapp-email-mcp-app.principal_id

  depends_on = [
    module.containerapp-email-mcp-app,
    module.keyvault
  ]
}
