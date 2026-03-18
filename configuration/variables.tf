variable "subscription_id" {
  description = "Enter an Azure subscription ID. Leave blank to use the default Azure Sponsorship subscription. You can find your subscription ID in the Azure Portal under 'Subscriptions'."
  type        = string
}

variable "stage" {
  description = "The deployment stage (e.g., sandbox,dev, test, prod)"
  type        = string
  default     = "sandbox"
}

variable "product_name" {
  description = <<EOF
                    The name of the product scope that encompasses the resources in the resource group.
                    Max 8 characters. Such as: repos, accr, admin, defer, etc.
                  EOF
  type        = string

  validation {
    condition     = length(var.product_name) <= 8
    error_message = "Product name must be 8 characters or less."
  }
}

### Network Resources ###


variable "nsg_name_prefix" {
  type        = string
  default     = "nsg"
  description = "Prefix of the Network Security Group names."
}

variable "acr_name_prefix" {
  type        = string
  default     = "acr"
  description = "Prefix of the acr name that is unique in your Azure subscription."
}

variable "env_name" {
  type        = string
  default     = "poc"
  description = "Environment name."
}

variable "additional_tags" {
  description = "Additional tags to merge with default tags. Can override default tags including data-classification."
  type        = map(string)
  default     = {}
}

variable "enable_network_restrictions" {
  description = "Enable network restrictions on Azure resources. Requires OIDC authentication for deployments."
  type        = bool
  default     = false
}

variable "keyvault_name_prefix" {
  type        = string
  default     = "kv"
  description = "Prefix of the Key Vault name."
}

variable "log_analytics_workspace_name_prefix" {
  type        = string
  default     = "log"
  description = "Prefix of the Log Analytics Workspace name."
}

variable "container_app_environment_name_prefix" {
  type        = string
  default     = "cae"
  description = "Prefix of the container app environment."
}

variable "container_app_name_prefix" {
  type        = string
  default     = "ca"
  description = "Prefix of the container app."
}

variable "entraid_application_client_id" {
  type        = string
  default     = ""
  description = "Application ID of the Agentic Foundation App Registration (provided by admins)"
}
