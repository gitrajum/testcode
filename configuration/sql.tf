/*
variable "sql_server_name" {
  description = "Name of the Azure SQL Server"
  type        = string
  default     = "afagentcell004-sqlsrv-001"
}

variable "sql_admin_username" {
  description = "Administrator username for SQL Server"
  type        = string
  default     = "sqladmin"
}

variable "sql_admin_password" {
  description = "Administrator password for SQL Server. Set via TF_VAR_sql_admin_password environment variable; do NOT store in VCS."
  type        = string
  sensitive   = true
  default     = null
}

resource "azurerm_mssql_server" "sql" {
  name                         = var.sql_server_name
  resource_group_name          = data.azurerm_resource_group.rg.name
  location                     = data.azurerm_resource_group.rg.location
  administrator_login          = var.sql_admin_username
  administrator_login_password = var.sql_admin_password
  version                      = "12.0"
}

resource "azurerm_mssql_database" "test_db" {
  name        = "test"
  server_id   = azurerm_mssql_server.sql.id
  sku_name    = "Basic"
  collation   = "SQL_Latin1_General_CP1_CI_AS"
  max_size_gb = 2
}
*/
