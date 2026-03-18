variable "application_insights_name_prefix" {
  type        = string
  default     = "appi"
  description = "Prefix of the Application Insights name."
}

module "application_insights" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/applicationinsights?ref=v1.0.5"

  name                = "${var.application_insights_name_prefix}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  workspace_id        = module.log_analytics_workspace.id

  application_type  = "web"
  retention_in_days = 90

  tags = local.tags

  depends_on = [
    module.log_analytics_workspace
  ]
}

/*
resource "azurerm_key_vault_secret" "application_insights_connection_string" {
  name         = "APPLICATIONINSIGHTS-CONNECTION-STRING"
  value        = nonsensitive(module.application_insights.connection_string)
  key_vault_id = module.keyvault.id
  content_type = "text/plain"

  # Set expiration date to maximum allowed (50 years from now)
  expiration_date = timeadd(timestamp(), "438000h") # 50 years = 438,000 hours

  depends_on = [
    module.application_insights,
    module.keyvault,
    azurerm_key_vault_access_policy.terraform_executor
  ]
}
*/

output "application_insights_id" {
  value       = module.application_insights.id
  description = "The ID of the Application Insights resource"
}

output "application_insights_instrumentation_key" {
  value       = module.application_insights.instrumentation_key
  description = "The instrumentation key for Application Insights"
  sensitive   = true
}

output "application_insights_connection_string" {
  value       = module.application_insights.connection_string
  description = "The connection string for Application Insights"
  sensitive   = true
}

output "application_insights_app_id" {
  value       = module.application_insights.app_id
  description = "The application ID of Application Insights"
}
