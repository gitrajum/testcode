module "log_analytics_workspace" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/log-analytics?ref=v1.0.5"

  name                = "${var.log_analytics_workspace_name_prefix}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name

  sku               = "PerGB2018"
  retention_in_days = 30
  # reservation_capacity_in_gb_per_day can only be used with sku = "CapacityReservation"
  # reservation_capacity_in_gb_per_day = 100

  tags = local.tags
}

output "log_analytics_workspace_id" {
  value       = module.log_analytics_workspace.id
  description = "The ID of the Log Analytics workspace"
}

output "log_analytics_workspace_workspace_id" {
  value       = module.log_analytics_workspace.workspace_id
  description = "The workspace (customer) ID of the Log Analytics workspace"
}
