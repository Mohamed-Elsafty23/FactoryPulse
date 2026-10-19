resource "random_string" "suffix" {
  length  = 6
  lower   = true
  upper   = false
  numeric = true
  special = false
}

locals {
  suffix = random_string.suffix.result

  rg_name      = "rg-${var.project}-${var.environment}"
  storage_name = substr("st${replace(var.project, "-", "")}${local.suffix}", 0, 24)
  kv_name      = substr("kv-${var.project}-${local.suffix}", 0, 24)
  sql_name     = "sql-${var.project}-${local.suffix}"
  adf_name     = "adf-${var.project}-${local.suffix}"
  dbw_name     = "dbw-${var.project}-${var.environment}"
  law_name     = "law-${var.project}-${local.suffix}"

  lake_directories = ["landing", "bronze", "silver", "gold", "quarantine", "ops"]

  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}
