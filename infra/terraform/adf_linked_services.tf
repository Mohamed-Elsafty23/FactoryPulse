resource "azurerm_data_factory_linked_service_key_vault" "kv" {
  count = var.enable_data_factory ? 1 : 0

  name            = "ls_keyvault"
  data_factory_id = local.adf_id
  key_vault_id    = azurerm_key_vault.main.id

  depends_on = [time_sleep.wait_adf_rbac]
}

resource "azurerm_data_factory_linked_service_azure_sql_database" "sql" {
  count = var.enable_data_factory ? 1 : 0

  name            = "ls_azuresql_factorypulse"
  data_factory_id = local.adf_id

  connection_string = join(";", [
    "Data Source=tcp:${azurerm_mssql_server.main.fully_qualified_domain_name},1433",
    "Initial Catalog=${azurerm_mssql_database.main.name}",
    "User ID=${var.sql_admin_user}",
    "Integrated Security=False",
    "Encrypt=True",
    "Connect Timeout=120",
  ])

  key_vault_password {
    linked_service_name = azurerm_data_factory_linked_service_key_vault.kv[0].name
    secret_name         = azurerm_key_vault_secret.sql_admin_password.name
  }
}

resource "azurerm_data_factory_linked_service_data_lake_storage_gen2" "adls" {
  count = var.enable_data_factory ? 1 : 0

  name                 = "ls_adls_lake"
  data_factory_id      = local.adf_id
  url                  = "https://${azurerm_storage_account.lake.name}.dfs.core.windows.net"
  use_managed_identity = true

  depends_on = [time_sleep.wait_adf_rbac]
}
