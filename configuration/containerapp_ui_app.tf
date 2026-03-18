# variable "container_app_ui_app_environment_name_prefix" {
#   #default     = "cae-uiapp"
#   description = "Prefix of the container app environment."
# }

variable "container_app_ui_app_name" {
  type        = string
  default     = "uiapp"
  description = "Name of the UI container app."
}

variable "container_app_ui_listening_port" {
  type        = number
  default     = 3000
  description = "Port the UI container app listens on."
}

module "containerapp-ui-app" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/containerapp?ref=v1.0.5"

  # Use abbreviated suffix to stay within 32-character limit
  container_app_name  = "${var.container_app_name_prefix}-${var.container_app_ui_app_name}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags

  log_analytics_workspace_id = module.log_analytics_workspace.id

  # Use the same Container Apps Environment as the agent for secure internal communication
  container_app_environment_id = module.container_app_environment.id

  image_name     = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" # Placeholder image - real image updated via CI/CD
  container_name = "ui-app"

  # Registry configuration for ACR with user-assigned identity
  registry_name      = azurerm_container_registry.acr.login_server
  registry_user_name = null
  registry_password  = null
  registry_identity  = azurerm_user_assigned_identity.acr_pull_identity.id

  ingress = {
    target_port = var.container_app_ui_listening_port # Must match the port your app listens on (hello world app uses port 80)
  }

  # Resource allocation
  cpu    = 1
  memory = "2Gi"

  # Horizontal scaling configuration
  replica_limits = {
    min = 1
    max = 1
  }

  # User-assigned identity for ACR image pull
  user_assigned_identity_ids = [azurerm_user_assigned_identity.acr_pull_identity.id]

  # No IP restrictions - open access
  ip_restrictions = null

  # Environment variables
  environment_variables = {
    NEXT_PUBLIC_AZURE_CLIENT_ID    = "6a99f31c-bf54-4a3c-89e8-bb3e5b108a25"
    NEXT_PUBLIC_AZURE_TENANT_ID    = data.azurerm_client_config.current.tenant_id
    NEXT_PUBLIC_AZURE_REDIRECT_URI = "https://${var.container_app_name_prefix}-${var.container_app_ui_app_name}-${local.resource_name_suffix}.${module.container_app_environment.default_domain}"
    NEXT_PUBLIC_AZURE_API_SCOPE    = "${var.entraid_application_client_id}/.default"
    NEXT_PUBLIC_API_URL            = module.containerapp_agent.url
    NEXT_PUBLIC_WS_URL             = "wss://${module.containerapp_agent.fqdn}"
  }

  # Secrets from Key Vault
  secret_environment_variables = {}

  depends_on = [
    azurerm_container_registry.acr,
    azurerm_role_assignment.acr_pull_identity_acr_pull,
    module.log_analytics_workspace,
    module.keyvault,
    module.container_app_environment
  ]
}

output "containerapp_ui_app_url" {
  value       = module.containerapp-ui-app.url
  description = "The URL to access the container app"
}

output "containerapp_ui_app_name" {
  value       = module.containerapp-ui-app.name
  description = "The name of the container app"
}


# Grant Container App managed identity access to Key Vault secrets
resource "azurerm_role_assignment" "containerapp-ui-app_keyvault" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.containerapp-ui-app.principal_id

  depends_on = [
    module.containerapp-ui-app,
    module.keyvault
  ]
}

# Add redirect URI to Entra ID Application for OAuth authentication
# resource "azuread_application_redirect_uris" "ui_app" {
#   application_id = "/applications/${var.app_registration_object_id}"
#   type           = "SPA" # Single Page Application for Next.js
#
#   redirect_uris = [
#     "http://localhost:3001", # Local development
#     "https://ca-uiapp-finopsai-dev-gwc.lemonwave-898114e1.germanywestcentral.azurecontainerapps.io", # FinOps Dev
#     "https://ca-uiapp-finopsai-prod-gwc.icyglacier-c533a571.germanywestcentral.azurecontainerapps.io", # FinOps Prod
#     "https://ca-uiapp-repostings-prod-gwc.purplesand-549f5ba0.germanywestcentral.azurecontainerapps.io", # Repostings Prod
#     module.containerapp-ui-app.url # Current environment
#   ]
# }
# Important: This will remove the existing redirect URIs for:
#
# http://localhost:3001 (local development)
# Other environments (dev, prod)
# If you want to keep the existing URIs and add the new one, you need to include all of them in the configuration:
