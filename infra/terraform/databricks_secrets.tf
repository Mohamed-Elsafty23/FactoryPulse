resource "databricks_secret_scope" "kv" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name                     = var.project
  initial_manage_principal = "users"

  keyvault_metadata {
    resource_id = azurerm_key_vault.main.id
    dns_name    = azurerm_key_vault.main.vault_uri
  }

  # Without the AzureDatabricks SP's data-plane role, the scope is created
  # but every secret read 403s at job runtime.
  depends_on = [time_sleep.wait_dbx_kv_rbac]
}
