resource "azurerm_data_factory_dataset_azure_sql_table" "sql_generic" {
  count = var.enable_data_factory ? 1 : 0

  name              = "ds_sql_generic"
  data_factory_id   = local.adf_id
  linked_service_id = azurerm_data_factory_linked_service_azure_sql_database.sql[0].id

  parameters = {
    schemaName = "ops"
    tableName  = "machines"
  }

  schema = "@dataset().schemaName"
  table  = "@dataset().tableName"
}

resource "azurerm_data_factory_dataset_parquet" "adls_parquet" {
  count = var.enable_data_factory ? 1 : 0

  name            = "ds_adls_parquet"
  data_factory_id = local.adf_id

  linked_service_name = azurerm_data_factory_linked_service_data_lake_storage_gen2.adls[0].name

  parameters = {
    folderPath = "landing/machines"
    fileName   = "machines.parquet"
  }

  azure_blob_fs_location {
    file_system              = azurerm_storage_data_lake_gen2_filesystem.lake.name
    path                     = "@dataset().folderPath"
    dynamic_path_enabled     = true
    filename                 = "@dataset().fileName"
    dynamic_filename_enabled = true
  }

  compression_codec = "snappy"
}
