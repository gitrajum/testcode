# Network Security Groups Configuration
# Phase 1: Network Foundation - NSGs and Rules
# Created: 2025-12-20

# ============================================================================
# NSG for Container Apps Subnet
# ============================================================================

resource "azurerm_network_security_group" "containerapp" {
  name                = "${var.nsg_name_prefix}-containerapp-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags
}

# Inbound Rules for Container Apps
resource "azurerm_network_security_rule" "containerapp_allow_webapp" {
  name                        = "Allow-WebApp-to-ContainerApp"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "10.10.2.0/24"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

resource "azurerm_network_security_rule" "containerapp_allow_pe" {
  name                        = "Allow-PrivateEndpoints-ContainerApp"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "10.10.3.0/24"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

resource "azurerm_network_security_rule" "containerapp_allow_lb" {
  name                        = "Allow-AzureLoadBalancer"
  priority                    = 120
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "AzureLoadBalancer"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

resource "azurerm_network_security_rule" "containerapp_deny_inbound" {
  name                        = "Deny-All-Inbound"
  priority                    = 4096
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

# Outbound Rules for Container Apps
resource "azurerm_network_security_rule" "containerapp_allow_out_pe" {
  name                        = "Allow-to-PrivateEndpoints"
  priority                    = 100
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "10.10.3.0/24"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

# Note: This rule may become unnecessary once ACR uses Private Endpoint
# Traffic will then flow through the PE subnet (10.10.3.0/24) instead
resource "azurerm_network_security_rule" "containerapp_allow_out_acr" {
  name                        = "Allow-ACR"
  priority                    = 110
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "AzureContainerRegistry.GermanyWestCentral"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

# Allow access to Azure Storage for Azure File Share (SMB)
resource "azurerm_network_security_rule" "containerapp_allow_out_storage" {
  name                        = "Allow-Storage-SMB"
  priority                    = 115
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "445"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "Storage.GermanyWestCentral"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

resource "azurerm_network_security_rule" "containerapp_allow_out_monitor" {
  name                        = "Allow-AzureMonitor"
  priority                    = 120
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "AzureMonitor"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

resource "azurerm_network_security_rule" "containerapp_allow_out_internet" {
  name                        = "Allow-Internet-HTTPS"
  priority                    = 130
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "Internet"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

resource "azurerm_network_security_rule" "containerapp_deny_outbound" {
  name                        = "Deny-All-Outbound"
  priority                    = 4096
  direction                   = "Outbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.containerapp.name
}

# ============================================================================
# NSG for Web App Subnet
# ============================================================================

resource "azurerm_network_security_group" "webapp" {
  name                = "${var.nsg_name_prefix}-webapp-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags
}

# Inbound Rules for Web App
resource "azurerm_network_security_rule" "webapp_allow_https" {
  name                        = "Allow-Internet-HTTPS"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "Internet"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

resource "azurerm_network_security_rule" "webapp_allow_lb" {
  name                        = "Allow-AzureLoadBalancer"
  priority                    = 120
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "AzureLoadBalancer"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

resource "azurerm_network_security_rule" "webapp_deny_inbound" {
  name                        = "Deny-All-Inbound"
  priority                    = 4096
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

# Outbound Rules for Web App
resource "azurerm_network_security_rule" "webapp_allow_out_containerapp" {
  name                        = "Allow-to-ContainerApp"
  priority                    = 100
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "10.10.0.0/23"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

resource "azurerm_network_security_rule" "webapp_allow_out_pe" {
  name                        = "Allow-to-PrivateEndpoints"
  priority                    = 110
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "10.10.3.0/24"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

resource "azurerm_network_security_rule" "webapp_allow_out_monitor" {
  name                        = "Allow-AzureMonitor"
  priority                    = 120
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "AzureMonitor"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

resource "azurerm_network_security_rule" "webapp_allow_out_internet" {
  name                        = "Allow-Outbound-Internet-HTTPS"
  priority                    = 130
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "Internet"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

resource "azurerm_network_security_rule" "webapp_deny_outbound" {
  name                        = "Deny-All-Outbound"
  priority                    = 4096
  direction                   = "Outbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.webapp.name
}

# ============================================================================
# NSG for Private Endpoints Subnet
# Note: While Microsoft states NSGs are optional for Private Endpoint subnets,
# organizational security policy AZ.CSR.NET.04a requires ALL subnets to have NSGs
# for defense-in-depth security posture
# ============================================================================

resource "azurerm_network_security_group" "privateendpoints" {
  name                = "${var.nsg_name_prefix}-privateendpoints-${local.resource_name_suffix}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags
}

# Inbound Rules for Private Endpoints
resource "azurerm_network_security_rule" "pe_allow_containerapp" {
  name                        = "Allow-ContainerApp-to-PE"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "10.10.0.0/23"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.privateendpoints.name
}

resource "azurerm_network_security_rule" "pe_allow_webapp" {
  name                        = "Allow-WebApp-to-PE"
  priority                    = 110
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "10.10.2.0/24"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.privateendpoints.name
}

resource "azurerm_network_security_rule" "pe_allow_devops" {
  name                        = "Allow-DevOps-to-PE"
  priority                    = 120
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "10.10.5.0/27"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.privateendpoints.name
}

resource "azurerm_network_security_rule" "pe_deny_inbound" {
  name                        = "Deny-All-Inbound"
  priority                    = 4096
  direction                   = "Inbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.privateendpoints.name
}

# Outbound Rules for Private Endpoints
resource "azurerm_network_security_rule" "pe_allow_response" {
  name                        = "Allow-PE-Response"
  priority                    = 100
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.privateendpoints.name
}

resource "azurerm_network_security_rule" "pe_deny_outbound" {
  name                        = "Deny-All-Outbound"
  priority                    = 4096
  direction                   = "Outbound"
  access                      = "Deny"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "*"
  destination_address_prefix  = "*"
  resource_group_name         = data.azurerm_resource_group.rg.name
  network_security_group_name = azurerm_network_security_group.privateendpoints.name
}

# ============================================================================
# NSG for Management Subnet
# Note: Commented out until Azure Bastion is deployed
# When implementing Bastion, proper rules are required:
# - Inbound: 443 from Internet, 443/8080 from GatewayManager
# - Outbound: 22/3389 to VNet, 443 to AzureCloud
# ============================================================================

# resource "azurerm_network_security_group" "management" {
#   name                = "${var.nsg_name_prefix}-management-${local.resource_name_suffix}"
#   location            = data.data.azurerm_resource_group.rg.location
#   resource_group_name = data.azurerm_resource_group.rg.name
#   tags                = local.tags
# }

# # Inbound Rules for Management (Bastion future use)
# resource "azurerm_network_security_rule" "mgmt_deny_inbound" {
#   name                        = "Deny-All-Inbound"
#   priority                    = 4096
#   direction                   = "Inbound"
#   access                      = "Deny"
#   protocol                    = "*"
#   source_port_range           = "*"
#   destination_port_range      = "*"
#   source_address_prefix       = "*"
#   destination_address_prefix  = "*"
#   resource_group_name         = data.azurerm_resource_group.rg.name
#   network_security_group_name = azurerm_network_security_group.management.name
# }

# # Outbound Rules for Management
# resource "azurerm_network_security_rule" "mgmt_allow_vnet" {
#   name                        = "Allow-to-VNet"
#   priority                    = 100
#   direction                   = "Outbound"
#   access                      = "Allow"
#   protocol                    = "*"
#   source_port_range           = "*"
#   destination_port_range      = "*"
#   source_address_prefix       = "VirtualNetwork"
#   destination_address_prefix  = "VirtualNetwork"
#   resource_group_name         = data.azurerm_resource_group.rg.name
#   network_security_group_name = azurerm_network_security_group.management.name
# }

# resource "azurerm_network_security_rule" "mgmt_allow_internet" {
#   name                        = "Allow-Internet-HTTPS"
#   priority                    = 110
#   direction                   = "Outbound"
#   access                      = "Allow"
#   protocol                    = "Tcp"
#   source_port_range           = "*"
#   destination_port_range      = "443"
#   source_address_prefix       = "VirtualNetwork"
#   destination_address_prefix  = "Internet"
#   resource_group_name         = data.azurerm_resource_group.rg.name
#   network_security_group_name = azurerm_network_security_group.management.name
# }

# resource "azurerm_network_security_rule" "mgmt_deny_outbound" {
#   name                        = "Deny-All-Outbound"
#   priority                    = 4096
#   direction                   = "Outbound"
#   access                      = "Deny"
#   protocol                    = "*"
#   source_port_range           = "*"
#   destination_port_range      = "*"
#   source_address_prefix       = "*"
#   destination_address_prefix  = "*"
#   resource_group_name         = data.azurerm_resource_group.rg.name
#   network_security_group_name = azurerm_network_security_group.management.name
# }

# ============================================================================
# NSG Associations with Subnets
# ============================================================================

resource "azurerm_subnet_network_security_group_association" "containerapp" {
  subnet_id                 = azurerm_subnet.containerapp.id
  network_security_group_id = azurerm_network_security_group.containerapp.id
}

resource "azurerm_subnet_network_security_group_association" "webapp" {
  subnet_id                 = azurerm_subnet.webapp.id
  network_security_group_id = azurerm_network_security_group.webapp.id
}

# Private Endpoints subnet NSG association (required by AZ.CSR.NET.04a)
resource "azurerm_subnet_network_security_group_association" "privateendpoints" {
  subnet_id                 = azurerm_subnet.privateendpoints.id
  network_security_group_id = azurerm_network_security_group.privateendpoints.id
}

# Management NSG commented out until Bastion is deployed
# resource "azurerm_subnet_network_security_group_association" "management" {
#   subnet_id                 = azurerm_subnet.management.id
#   network_security_group_id = azurerm_network_security_group.management.id
# }

# ============================================================================
# Outputs
# ============================================================================

output "nsg_containerapp_id" {
  value       = azurerm_network_security_group.containerapp.id
  description = "The ID of the Container App NSG"
}

output "nsg_webapp_id" {
  value       = azurerm_network_security_group.webapp.id
  description = "The ID of the Web App NSG"
}

output "nsg_privateendpoints_id" {
  value       = azurerm_network_security_group.privateendpoints.id
  description = "The ID of the Private Endpoints NSG"
}

# output "nsg_management_id" {
#   value       = azurerm_network_security_group.management.id
#   description = "The ID of the Management NSG"
# }
