# Azure Communication Service for outbound email
# Used for sending emails via SDK/API from Python applications

## Warning: Make sure the Microsoft.Communication provider is registered in your subscription
# Azure requires you to explicitly register resource providers before you can create resources of that type.
# $ az provider register --namespace Microsoft.Communication
##

resource "azurerm_email_communication_service" "email" {
  name                = "ecs-${local.resource_name_suffix}"
  resource_group_name = data.azurerm_resource_group.rg.name
  data_location       = "Germany"

  tags = local.tags
}

# Azure Communication Service linked to the email service
resource "azurerm_communication_service" "communication" {
  name                = "acs-${local.resource_name_suffix}"
  resource_group_name = data.azurerm_resource_group.rg.name
  data_location       = "Germany"

  tags = local.tags
}

### Email Communication ###
variable "custom_email_domain" {
  type        = string
  description = "Custom domain for sending emails (e.g., 'yourdomain.com'). Leave empty to use Azure managed domain."
  default     = ""
}

variable "use_custom_email_domain" {
  type        = bool
  description = "Whether to actively link the custom domain (true) or default domain (false) to the communication service. Only applies if custom_email_domain is set."
  default     = false
}

# Azure Managed Domain (default, free)
resource "azurerm_email_communication_service_domain" "default" {
  name             = "AzureManagedDomain"
  email_service_id = azurerm_email_communication_service.email.id

  domain_management = "AzureManaged"

  tags = local.tags
}

# Custom Domain (requires DNS configuration)
resource "azurerm_email_communication_service_domain" "custom" {
  count            = var.custom_email_domain != "" ? 1 : 0
  name             = var.custom_email_domain
  email_service_id = azurerm_email_communication_service.email.id

  domain_management = "CustomerManaged"

  tags = local.tags
}

# It is necessary to connect the email domain to the communication service
resource "azurerm_communication_service_email_domain_association" "link" {
  communication_service_id = azurerm_communication_service.communication.id
  email_service_domain_id  = (var.custom_email_domain != "" && var.use_custom_email_domain) ? azurerm_email_communication_service_domain.custom[0].id : azurerm_email_communication_service_domain.default.id
}
