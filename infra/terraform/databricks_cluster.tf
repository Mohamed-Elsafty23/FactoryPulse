resource "databricks_cluster" "dev" {
  count    = var.enable_databricks && var.enable_classic_databricks_cluster ? 1 : 0
  provider = databricks.workspace

  cluster_name  = "${var.project}-dev"
  spark_version = "15.4.x-scala2.12"
  node_type_id  = var.databricks_node_type

  autotermination_minutes = var.cluster_autotermination_minutes
  num_workers             = 0
  data_security_mode      = "SINGLE_USER"
  single_user_name        = data.databricks_current_user.me[0].user_name

  spark_conf = {
    "spark.master"                             = "local[*, 4]"
    "spark.databricks.cluster.profile"         = "singleNode"
    "spark.sql.session.timeZone"               = "UTC"
    "spark.sql.sources.partitionOverwriteMode" = "dynamic"
  }

  custom_tags = {
    ResourceClass = "SingleNode"
    project       = var.project
  }
}

output "databricks_cluster_id" {
  value = var.enable_databricks && var.enable_classic_databricks_cluster ? databricks_cluster.dev[0].id : null
}
