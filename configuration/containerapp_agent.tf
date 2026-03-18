variable "container_app_agent_name" {
  type        = string
  default     = "agent"
  description = "Name of the container app."
}

variable "agent_app_authentication_enabled" {
  type        = bool
  default     = true
  description = "Enable authentication for the agent app"
}

variable "agent_app_authentication_require_auth" {
  type        = bool
  default     = true
  description = "Require authentication for the agent app"
}

variable "agent_debugpy_enable" {
  type        = bool
  default     = false
  description = "Enable debugpy for remote debugging"
}

variable "agent_debugpy_wait" {
  type        = bool
  default     = false
  description = "Wait for debugger to attach before starting"
}

variable "agent_temp_dir" {
  type        = string
  default     = "/tmp/agentic_ai"
  description = "Directory for temporary file downloads from MCP tools"
}

variable "container_app_agent_listening_port" {
  type        = number
  default     = 8000
  description = "Port the Agent container app listens on."
}

variable "azure_apim_sub_key" {
  type        = string
  description = "Azure APIM subscription key for OpenAI access"
  default     = "update_key_here"
}

variable "databricks_token" {
  type        = string
  description = "Azure APIM subscription key for OpenAI access"
  default     = "update_key_here"
}

### Observability Configuration ###
variable "observability_enable_tracing" {
  description = "Enable distributed tracing for observability"
  type        = bool
  default     = false
}

variable "observability_enable_metrics" {
  description = "Enable metrics collection for observability"
  type        = bool
  default     = false
}

variable "observability_enable_logging" {
  description = "Enable enhanced logging for observability"
  type        = bool
  default     = false
}

module "containerapp_agent" {
  #source = "../../../agentic_foundation_terraform_modules/modules/azure/containerapp"
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/containerapp?ref=v1.0.9"

  # Use abbreviated suffix to stay within 32-character limit
  container_app_name  = "${var.container_app_name_prefix}-${var.container_app_agent_name}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags

  log_analytics_workspace_id = module.log_analytics_workspace.id

  # Define volumes with mount configuration
  volumes = [
    {
      name         = "agent-volume"
      storage_type = "AzureFile"
      storage_name = "agentfilestorage"
      mount_path   = "/mnt/agentfiles"
    }
  ]

  container_app_environment_id = module.container_app_environment.id
  image_name                   = "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" # Placeholder image - real image updated via CI/CD
  container_name               = "agentic-ai-app"

  # Registry configuration for ACR with user-assigned identity
  registry_name      = azurerm_container_registry.acr.login_server
  registry_user_name = null
  registry_password  = null
  registry_identity  = azurerm_user_assigned_identity.acr_pull_identity.id

  ingress = {
    target_port = var.container_app_agent_listening_port # Change this to match your app's port (e.g., 8080, 3000, etc.)
  }

  workload_profile_name = module.container_app_environment.workload_profile_name

  # Resource allocation - increased for E32 workload profile
  cpu    = 32.0
  memory = "256Gi"

  # Horizontal scaling configuration
  replica_limits = {
    min = 1
    max = 1
  }

  # User-assigned identity for ACR image pull
  user_assigned_identity_ids = [azurerm_user_assigned_identity.acr_pull_identity.id]

  # Environment variables
  environment_variables = merge({
    # Feature flags
    ENV_VAR_FROM_AZAPI               = "true"
    APP_AUTHENTICATION__ENABLED      = tostring(var.agent_app_authentication_enabled)
    APP_AUTHENTICATION__REQUIRE_AUTH = tostring(var.agent_app_authentication_require_auth)
    
    # Timeout settings for long-running PDF processing
    FASTAPI_TIMEOUT                   = "36000"  # 10 hours
    UVICORN_TIMEOUT_KEEP_ALIVE        = "36000"  # 10 hours
    UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN = "300"  # 5 minutes
    DEBUGPY_ENABLE                    = tostring(var.agent_debugpy_enable)
    DEBUGPY_WAIT                      = tostring(var.agent_debugpy_wait)

    # Observability Configuration
    OBSERVABILITY_ENABLE_TRACING = tostring(var.observability_enable_tracing)
    OBSERVABILITY_ENABLE_METRICS = tostring(var.observability_enable_metrics)
    OBSERVABILITY_ENABLE_LOGGING = tostring(var.observability_enable_logging)

    # Azure OpenAI Configuration
    AZURE_OPENAI_ENDPOINT        = "https://apim-af-dev-ca3d.azure-api.net"
    AZURE_OPENAI_DEPLOYMENT_NAME = "gpt-5-mini"
    AZURE_OPENAI_API_VERSION     = "2024-12-01-preview"

    #Databricks configuration
    DATABRICKS_HOST      = "adb-4071335540424391.11.azuredatabricks.net"
    DATABRICKS_HTTP_PATH = "/sql/1.0/warehouses/916c447fdd11cd1e"
    DATABRICKS_CATALOG   = "efdataonelh_prd"
    DATABRICKS_SCHEMA    = "generaldiscovery_servicenow_r"

    AZURE_STORAGE_ACCOUNT_NAME = "samobcontrpocgwc"
    FINGERPRINT_BACKEND        = "azure_table"
    RULES_CACHE_DIR            = "/mnt/agentfiles/rules_cache"

    # App URLs - AGENT_URL derived from known values to avoid circular dependency
    AGENT_URL = "https://${var.container_app_name_prefix}-${var.container_app_agent_name}-${local.resource_name_suffix}.${module.container_app_environment.default_domain}"

    # Azure Identity
    AZURE_TENANT_ID = data.azurerm_client_config.current.tenant_id
    AZURE_CLIENT_ID = var.entraid_application_client_id

    # Agent File Storage Configuration
    AGENT_TEMP_DIR = var.agent_temp_dir

    # MCP Configuration
    ELSA_MCP_ENDPOINT               = "http://${module.containerapp_mcp_elsa.name}:${var.container_app_mcp_elsa_listening_port}/mcp"
    #    MCP_EMAIL_ENDPOINT                      = "http://${module.containerapp-email-mcp-app.name}/mcp"
    #    MCP_EMAIL_AUDIENCE                      = var.mcp_email_audience
    #    EMAIL_MCP_USE_USER_TOKEN                = tostring(var.mcp_email_use_user_token)
    #    EMAIL_MCP_USE_MANAGED_IDENTITY          = tostring(var.mcp_email_use_managed_identity)

    # Alternate naming for backward compatibility with .env.example
    #    EMAIL_MCP_ENDPOINT                      = "http://${module.containerapp-email-mcp-app.name}/mcp"
    #    EMAIL_MCP_AUDIENCE                      = var.mcp_email_audience
    },
  )

  # Pass actual secret values from Key Vault Terraform resources
  # This avoids the Key Vault reference validation issue during Container App creation
  secret_environment_variables = merge({
    AZURE_OPENAI_API_KEY                  = var.azure_apim_sub_key
    APPLICATIONINSIGHTS_CONNECTION_STRING = module.application_insights.connection_string
    DATABRICKS_TOKEN                      = var.databricks_token
    # AZURE_STORAGE_CONNECTION_STRING       = azurerm_storage_account.agent_storage.primary_connection_string
    # AZURE_STORAGE_ACCOUNT_KEY             = azurerm_storage_account.agent_storage.primary_access_key
    },
  )

  depends_on = [
    azurerm_container_registry.acr,
    azurerm_role_assignment.acr_pull_identity_acr_pull,
    module.log_analytics_workspace,
    module.keyvault,
    module.application_insights,
    module.container_app_environment,
    azurerm_container_app_environment_storage.agent_storage
  ]
}

# Grant Container App managed identity access to Key Vault secrets
resource "azurerm_role_assignment" "containerapp_agent_keyvault" {
  scope                = module.keyvault.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = module.containerapp_agent.principal_id

  depends_on = [
    module.containerapp_agent,
    module.keyvault
  ]
}

resource "azurerm_role_assignment" "containerapp_agent_app_insights" {
  scope                = module.application_insights.id
  role_definition_name = "Monitoring Metrics Publisher"
  principal_id         = module.containerapp_agent.principal_id

  depends_on = [
    module.containerapp_agent,
    module.application_insights
  ]
}

# Outputs for the container app agent
output "containerapp_agent_url" {
  value       = module.containerapp_agent.url
  description = "The URL to access the container app"
}

output "containerapp_agent_name" {
  value       = module.containerapp_agent.name
  description = "The name of the container app"
}

output "containerapp_agent_identity_principal_id" {
  value       = module.containerapp_agent.principal_id
  description = "The principal ID (object ID) of the container app managed identity"
}

output "containerapp_agent_identity_tenant_id" {
  value       = data.azurerm_client_config.current.tenant_id
  description = "The tenant ID of the Azure subscription"
}
