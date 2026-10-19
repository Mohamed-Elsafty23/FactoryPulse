locals {
  grp_eng = "factorypulse_engineers"
  grp_anl = "factorypulse_analysts"
  grp_mgr = "factorypulse_plant_managers"
}

data "databricks_current_user" "me" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace
}

resource "databricks_grants" "catalog_dev" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  catalog = databricks_catalog.dev[0].name

  grant {
    principal  = local.grp_eng
    privileges = ["ALL_PRIVILEGES"]
  }
  grant {
    principal  = local.grp_anl
    privileges = ["USE_CATALOG"]
  }
  grant {
    principal  = local.grp_mgr
    privileges = ["USE_CATALOG"]
  }

}

resource "databricks_grants" "gold" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  schema = "${databricks_catalog.dev[0].name}.${databricks_schema.dev["gold"].name}"

  grant {
    principal  = local.grp_anl
    privileges = ["USE_SCHEMA", "SELECT"]
  }
  grant {
    principal  = local.grp_mgr
    privileges = ["USE_SCHEMA", "SELECT"]
  }

  depends_on = [databricks_grants.catalog_dev]
}

resource "databricks_grants" "ops" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  schema = "${databricks_catalog.dev[0].name}.${databricks_schema.dev["ops"].name}"

  grant {
    principal  = local.grp_anl
    privileges = ["USE_SCHEMA", "SELECT"]
  }

  depends_on = [databricks_grants.catalog_dev]
}

resource "databricks_grants" "restricted" {
  for_each = var.enable_databricks ? toset(["bronze", "silver", "quarantine"]) : toset([])
  provider = databricks.workspace

  schema = "${databricks_catalog.dev[0].name}.${databricks_schema.dev[each.key].name}"

  grant {
    principal  = local.grp_eng
    privileges = ["ALL_PRIVILEGES"]
  }

  depends_on = [databricks_grants.catalog_dev]
}
