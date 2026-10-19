output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "location" {
  value = azurerm_resource_group.main.location
}

output "storage_account_name" {
  value = azurerm_storage_account.lake.name
}

output "lake_filesystem" {
  value = azurerm_storage_data_lake_gen2_filesystem.lake.name
}

output "abfss_root" {
  description = "ADLS Gen2 lake root URI."
  value       = "abfss://lake@${azurerm_storage_account.lake.name}.dfs.core.windows.net"
}

output "key_vault_name" {
  value = azurerm_key_vault.main.name
}

output "key_vault_id" {
  value = azurerm_key_vault.main.id
}

output "sql_server_fqdn" {
  value = azurerm_mssql_server.main.fully_qualified_domain_name
}

output "sql_database_name" {
  value = azurerm_mssql_database.main.name
}

output "sql_admin_user" {
  value = var.sql_admin_user
}

output "sql_admin_password" {
  value     = random_password.sql_admin.result
  sensitive = true
}

output "data_factory_name" {
  value = var.enable_data_factory ? azurerm_data_factory.main[0].name : null
}

output "data_factory_studio_url" {
  value = var.enable_data_factory ? "https://adf.azure.com/en/home?factory=${azurerm_data_factory.main[0].id}" : null
}

output "databricks_workspace_url" {
  value = var.enable_databricks ? "https://${azurerm_databricks_workspace.main[0].workspace_url}" : null
}

output "databricks_access_connector_id" {
  value = var.enable_databricks ? azurerm_databricks_access_connector.main[0].id : null
}
