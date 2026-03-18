# Virtual Network Configuration
# Phase 1: Network Foundation - Virtual Network and Subnets

variable "vnet_name_prefix" {
  type        = string
  default     = "vnet"
  description = "Prefix of the Virtual Network name."
}

variable "subnet_name_prefix" {
  type        = string
  default     = "snet"
  description = "Prefix of the subnet names."
}

# Virtual Network
resource "azurerm_virtual_network" "main" {
  name                = "${var.vnet_name_prefix}-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  address_space       = ["10.10.0.0/16"]

  tags = local.tags
}

# Subnet for Container Apps Environment
# Requires minimum /27, using /23 for workload profiles support
resource "azurerm_subnet" "containerapp" {
  name                 = "${var.subnet_name_prefix}-containerapp-${local.resource_name_suffix}"
  resource_group_name  = data.azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.0.0/23"]

  # Enable service endpoints for Azure services
  service_endpoints = ["Microsoft.CognitiveServices", "Microsoft.Storage"]

  # Delegation for Container Apps Environment
  delegation {
    name = "delegation-containerapp"

    service_delegation {
      name = "Microsoft.App/environments"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }
}

# Subnet for App Service VNet Integration
resource "azurerm_subnet" "webapp" {
  name                 = "${var.subnet_name_prefix}-webapp-${local.resource_name_suffix}"
  resource_group_name  = data.azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.2.0/24"]

  # Delegation for App Service
  delegation {
    name = "delegation-webapp"

    service_delegation {
      name = "Microsoft.Web/serverFarms"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
      ]
    }
  }

  # Ignore changes to delegation actions due to Azure API inconsistency
  lifecycle {
    ignore_changes = [
      delegation[0].service_delegation[0].actions,
    ]
  }
}

# Subnet for Private Endpoints
resource "azurerm_subnet" "privateendpoints" {
  name                 = "${var.subnet_name_prefix}-privateendpoints-${local.resource_name_suffix}"
  resource_group_name  = data.azurerm_resource_group.rg.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.3.0/24"]

  # Network policies must be disabled for Private Endpoints
  private_endpoint_network_policies = "Disabled"
}

# Subnet for Management Resources (Bastion, Jump Boxes)
# Commented out until Bastion is deployed
# resource "azurerm_subnet" "management" {
#   name                 = "${var.subnet_name_prefix}-management-${local.resource_name_suffix}"
#   resource_group_name  = azurerm_resource_group.rg.name
#   virtual_network_name = azurerm_virtual_network.main.name
#   address_prefixes     = ["10.10.4.0/27"]
# }

# Subnet for DevOps Agents
# Commented out - only needed for self-hosted Azure DevOps agents in VNet
# resource "azurerm_subnet" "devops" {
#   name                 = "${var.subnet_name_prefix}-devops-${local.resource_name_suffix}"
#   resource_group_name  = azurerm_resource_group.rg.name
#   virtual_network_name = azurerm_virtual_network.main.name
#   address_prefixes     = ["10.10.5.0/27"]
# }

# Outputs
output "vnet_id" {
  value       = azurerm_virtual_network.main.id
  description = "The ID of the Virtual Network"
}

output "vnet_name" {
  value       = azurerm_virtual_network.main.name
  description = "The name of the Virtual Network"
}

output "subnet_containerapp_id" {
  value       = azurerm_subnet.containerapp.id
  description = "The ID of the Container App subnet"
}

output "subnet_webapp_id" {
  value       = azurerm_subnet.webapp.id
  description = "The ID of the Web App subnet"
}

output "subnet_privateendpoints_id" {
  value       = azurerm_subnet.privateendpoints.id
  description = "The ID of the Private Endpoints subnet"
}

# output "subnet_management_id" {
#   value       = azurerm_subnet.management.id
#   description = "The ID of the Management subnet"
# }

# output "subnet_devops_id" {
#   value       = azurerm_subnet.devops.id
#   description = "The ID of the DevOps subnet"
# }
