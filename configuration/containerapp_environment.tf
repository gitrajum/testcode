# Shared Container App Environment for all container apps
# Creating this as a dedicated module ensures single-pass deployment and reusability
module "container_app_environment" {
  source = "git::https://github.com/bayer-int/agentic_foundation_terraform_modules.git//modules/azure/containerapp_environment?ref=v1.0.9"

  name                               = "${var.container_app_environment_name_prefix}-${local.resource_name_suffix}"
  location                           = data.azurerm_resource_group.rg.location
  resource_group_name                = data.azurerm_resource_group.rg.name
  log_analytics_workspace_id         = module.log_analytics_workspace.id
  subnet_id                          = azurerm_subnet.containerapp.id
  infrastructure_resource_group_name = "ME_${var.container_app_environment_name_prefix}-${local.resource_name_suffix}_${data.azurerm_resource_group.rg.name}_${data.azurerm_resource_group.rg.location}"

  # Workload profile configuration
  workload_profile_name          = "Dedicated"
  workload_profile_type          = "E32"
  workload_profile_minimum_count = 3
  workload_profile_maximum_count = 5

  tags = local.tags

  depends_on = [
    module.log_analytics_workspace,
    azurerm_subnet.containerapp
  ]
}

output "container_app_environment_id" {
  value       = module.container_app_environment.id
  description = "The ID of the shared container app environment"
}

output "container_app_environment_name" {
  value       = module.container_app_environment.name
  description = "The name of the shared container app environment"
}
