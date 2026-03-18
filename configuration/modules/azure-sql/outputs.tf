output "sql_server_name" {
  value = azurerm_mssql_server.sql_server.name
}

output "database_name" {
  value = azurerm_mssql_database.sql_db.name
}

output "key_vault_name" {
  value = azurerm_key_vault.kv.name
}
