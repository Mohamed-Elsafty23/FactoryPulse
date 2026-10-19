locals {
  uc_root = var.enable_databricks ? "abfss://${azurerm_storage_data_lake_gen2_filesystem.lake.name}@${azurerm_storage_account.lake.name}.dfs.core.windows.net" : null

  medallion_schemas = {
    bronze     = "Raw, immutable capture of source data. No business logic; lineage columns only."
    silver     = "Cleaned, typed, deduplicated and validated data."
    gold       = "Star schema and aggregates consumed by Power BI."
    quarantine = "Rejected rows with a reject_reason; append-only audit data."
    ops        = "Pipeline execution telemetry and governed artifacts."
  }
}

resource "databricks_catalog" "dev" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name         = "${var.project}_dev"
  comment      = "FactoryPulse development catalog for the manufacturing reliability lakehouse."
  storage_root = "${local.uc_root}/uc_managed_dev"
  properties   = { purpose = "development" }

  depends_on = [databricks_external_location.lake]
}

resource "databricks_catalog" "prod" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name         = "${var.project}_prod"
  comment      = "FactoryPulse production catalog."
  storage_root = "${local.uc_root}/uc_managed_prod"
  properties   = { purpose = "production" }

  depends_on = [databricks_external_location.lake]
}

resource "databricks_schema" "dev" {
  for_each = var.enable_databricks ? local.medallion_schemas : {}
  provider = databricks.workspace

  catalog_name  = databricks_catalog.dev[0].name
  name          = each.key
  comment       = each.value
  force_destroy = true
}

resource "databricks_schema" "prod" {
  for_each = var.enable_databricks ? local.medallion_schemas : {}
  provider = databricks.workspace

  catalog_name  = databricks_catalog.prod[0].name
  name          = each.key
  comment       = each.value
  force_destroy = true
}

resource "databricks_volume" "artifacts" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name         = "artifacts"
  catalog_name = databricks_catalog.dev[0].name
  schema_name  = databricks_schema.dev["ops"].name
  volume_type  = "MANAGED"
  comment      = "Versioned Python wheel artifacts used by FactoryPulse jobs."
}

output "wheel_volume_path" {
  value = var.enable_databricks ? "/Volumes/${databricks_catalog.dev[0].name}/ops/artifacts" : null
}
