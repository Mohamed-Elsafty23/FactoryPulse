resource "azurerm_data_factory_pipeline" "incremental_ingest" {
  count = var.enable_data_factory ? 1 : 0

  name            = "pl_incremental_ingest"
  data_factory_id = local.adf_id
  description     = "Metadata-driven incremental ingestion with closed watermark windows."

  parameters = {
    tableFilter = "*"
  }

  activities_json = file("${path.module}/adf_pipelines/incremental_ingest.json")

  depends_on = [
    azurerm_data_factory_dataset_azure_sql_table.sql_generic,
    azurerm_data_factory_dataset_parquet.adls_parquet,
  ]
}

resource "azurerm_data_factory_pipeline" "backfill" {
  count = var.enable_data_factory ? 1 : 0

  name            = "pl_backfill"
  data_factory_id = local.adf_id
  description     = "Re-runnable date-range backfill that never mutates ingestion_control."

  parameters = {
    sourceSchema    = "ops"
    sourceTable     = "work_orders"
    watermarkColumn = "updated_at"
    startDate       = "2025-10-01"
    endDate         = "2025-11-01"
    targetPath      = "landing/work_orders"
  }

  activities_json = file("${path.module}/adf_pipelines/backfill.json")

  depends_on = [
    azurerm_data_factory_dataset_azure_sql_table.sql_generic,
    azurerm_data_factory_dataset_parquet.adls_parquet,
  ]
}
