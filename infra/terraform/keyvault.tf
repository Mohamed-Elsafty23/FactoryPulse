resource "azurerm_key_vault" "main" {
  name                       = local.kv_name
  location                   = azurerm_resource_group.main.location
  resource_group_name        = azurerm_resource_group.main.name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  purge_protection_enabled   = false
  soft_delete_retention_days = 7
  tags                       = local.tags
}

resource "azurerm_role_assignment" "tf_kv" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "time_sleep" "wait_kv_rbac" {
  depends_on      = [azurerm_role_assignment.tf_kv]
  create_duration = "120s"
}

# ---------------------------------------------------------------------------
# A Key Vault-backed secret scope resolves secrets AT RUNTIME, as the
# first-party "AzureDatabricks" application -- not as the caller who created
# the scope. Creating the scope therefore succeeds while every
# dbutils.secrets.get() fails with 403 ForbiddenByRbac until this data-plane
# role exists.
#
# The app id below is a FIXED, well-known GUID, identical in every Azure
# tenant; the object id behind it is tenant-specific, hence the data source.
# ---------------------------------------------------------------------------
data "azuread_service_principal" "databricks" {
  count     = var.enable_databricks ? 1 : 0
  client_id = "2ff814a6-3304-4ab8-85cb-cd0e6f879c1d"
}

resource "azurerm_role_assignment" "databricks_kv_secrets" {
  count = var.enable_databricks ? 1 : 0

  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = data.azuread_service_principal.databricks[0].object_id
}

resource "time_sleep" "wait_dbx_kv_rbac" {
  count           = var.enable_databricks ? 1 : 0
  depends_on      = [azurerm_role_assignment.databricks_kv_secrets]
  create_duration = "120s"
}

resource "random_password" "sql_admin" {
  length           = 24
  special          = true
  override_special = "!#%*-_"
  min_upper        = 2
  min_lower        = 2
  min_numeric      = 2
  min_special      = 2
}

resource "azurerm_key_vault_secret" "sql_admin_password" {
  name         = "sql-admin-password"
  value        = random_password.sql_admin.result
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.wait_kv_rbac]
}

resource "azurerm_key_vault_secret" "sql_admin_user" {
  name         = "sql-admin-user"
  value        = var.sql_admin_user
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.wait_kv_rbac]
}

resource "azurerm_key_vault_secret" "adls_account_name" {
  name         = "adls-account-name"
  value        = azurerm_storage_account.lake.name
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.wait_kv_rbac]
}

resource "azurerm_key_vault_secret" "adls_account_key" {
  name         = "adls-account-key"
  value        = azurerm_storage_account.lake.primary_access_key
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.wait_kv_rbac]
}
