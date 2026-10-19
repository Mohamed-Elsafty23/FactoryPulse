resource "databricks_storage_credential" "lake" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name    = "cred_${var.project}"
  comment = "Managed identity credential for the FactoryPulse ADLS lake."

  azure_managed_identity {
    access_connector_id = azurerm_databricks_access_connector.main[0].id
  }

  depends_on = [time_sleep.wait_uc_rbac]
}

resource "databricks_external_location" "lake" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name            = "ext_${var.project}_lake"
  url             = "abfss://${azurerm_storage_data_lake_gen2_filesystem.lake.name}@${azurerm_storage_account.lake.name}.dfs.core.windows.net/"
  credential_name = databricks_storage_credential.lake[0].name
  comment         = "Root of the FactoryPulse medallion lake."

  depends_on = [time_sleep.wait_uc_rbac]
}
