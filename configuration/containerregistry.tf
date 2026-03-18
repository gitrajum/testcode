variable "allowed_ip_ranges" {
  description = "List of IP addresses or CIDR ranges to allow access to the container registry"
  type        = list(string)
  default     = []
}

locals {
  # append env_name to the ACR name
  acrname = "${var.acr_name_prefix}${var.product_name}${var.env_name}"
}

# TODO: Refactor to use module instead of direct resource
resource "azurerm_container_registry" "acr" {
  name                = local.acrname
  resource_group_name = data.azurerm_resource_group.rg.name
  location            = data.azurerm_resource_group.rg.location
  sku                 = "Premium" # Required for private endpoint support
  admin_enabled       = false     # Disabled to comply with policy

  # Security: Policies disabled to allow unsigned image pushes from GitHub Actions
  # Trust policy requires Notary signing which blocks standard docker push
  # Immutability enforced via workflow-level tag locking instead (see SECURITY_REMEDIATION_LOG.md)
  quarantine_policy_enabled = false
  retention_policy_in_days  = 30
  trust_policy_enabled      = false

  # Network security: Restrict public access when OIDC is enabled
  public_network_access_enabled = !var.enable_network_restrictions
  network_rule_bypass_option    = "AzureServices"

  # Apply network rules when restrictions are enabled
  # Note: VNet rules via network_rule_set are DEPRECATED in ACR
  # Container Apps must use Private Endpoints for VNet access (see commented block below)
  dynamic "network_rule_set" {
    for_each = var.enable_network_restrictions ? [1] : []
    content {
      default_action = "Deny"

      # Allow specific IP addresses (emergency access)
      ip_rule = [
        for ip in var.allowed_ip_ranges : {
          action   = "Allow"
          ip_range = ip
        }
      ]
    }
  }

  tags = local.tags
}

# Private Endpoint for ACR to allow VNet access from Container Apps
resource "azurerm_private_endpoint" "acr" {
  name                = "pe-${local.acrname}"
  location            = data.azurerm_resource_group.rg.location
  resource_group_name = data.azurerm_resource_group.rg.name
  subnet_id           = azurerm_subnet.privateendpoints.id

  private_service_connection {
    name                           = "pe-connection-${local.acrname}"
    private_connection_resource_id = azurerm_container_registry.acr.id
    subresource_names              = ["registry"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "default"
    private_dns_zone_ids = [azurerm_private_dns_zone.acr.id]
  }

  tags = local.tags
}

resource "azurerm_private_dns_zone" "acr" {
  name                = "privatelink.azurecr.io"
  resource_group_name = data.azurerm_resource_group.rg.name
  tags                = local.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "acr" {
  name                  = "acr-dns-link"
  resource_group_name   = data.azurerm_resource_group.rg.name
  private_dns_zone_name = azurerm_private_dns_zone.acr.name
  virtual_network_id    = azurerm_virtual_network.main.id
  tags                  = local.tags
}

# Role assignment for Github Actions to push & pull images to ACR
# NOTE: Requires the deploying service principal to have Owner or User Access Administrator role
resource "azurerm_role_assignment" "github_actions_acr_push" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "Contributor"
  principal_id         = "35d9f1fa-3eff-4c28-a8de-889fc9886a7d" # Object ID for Agentic Foundation 1 Enterprise Application in Azure AD

  depends_on = [azurerm_container_registry.acr]
}

# Assign AcrPull role to the shared user-assigned identity
# This identity is used by all container apps to pull images from ACR
resource "azurerm_role_assignment" "acr_pull_identity_acr_pull" {
  scope                = azurerm_container_registry.acr.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.acr_pull_identity.principal_id

  depends_on = [
    azurerm_user_assigned_identity.acr_pull_identity,
    azurerm_container_registry.acr
  ]
}

output "acr_name" {
  description = "The name of the container registry."
  value       = azurerm_container_registry.acr.name
}

output "acr_login_server" {
  description = "The URL that can be used to log into the container registry."
  value       = azurerm_container_registry.acr.login_server
}

output "acr_username" {
  description = "The Username associated with the Container Registry Admin account - if the admin account is enabled."
  value       = azurerm_container_registry.acr.admin_username
}

output "acr_password" {
  description = "The Password associated with the Container Registry Admin account - if the admin account is enabled."
  value       = azurerm_container_registry.acr.admin_password
  sensitive   = true
} # Find the password in the state file
