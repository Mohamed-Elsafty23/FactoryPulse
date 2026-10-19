locals {
  notebook_base = var.enable_databricks ? "/Users/${data.databricks_current_user.me[0].user_name}/factorypulse" : null
  # Version comes from a variable, not a literal: the serverless environment
  # resolves dependencies by path, so a rebuilt wheel at an UNCHANGED path can
  # be served from cache and silently run stale code. Bumping the version
  # changes the filename, which forces a genuine reinstall.
  wheel_path = var.enable_databricks ? "/Volumes/${databricks_catalog.dev[0].name}/ops/artifacts/factorypulse-${var.wheel_version}-py3-none-any.whl" : null
}

resource "databricks_job" "medallion" {
  count    = var.enable_databricks ? 1 : 0
  provider = databricks.workspace

  name                = "${var.project}-medallion"
  max_concurrent_runs = 1

  email_notifications {
    on_failure                = [var.workspace_admin_email]
    no_alert_for_skipped_runs = false
  }

  environment {
    environment_key = "factorypulse_env"
    spec {
      client       = "1"
      dependencies = [local.wheel_path]
    }
  }

  task {
    task_key                  = "bronze"
    environment_key           = "factorypulse_env"
    max_retries               = 2
    min_retry_interval_millis = 60000

    notebook_task {
      notebook_path   = "${local.notebook_base}/10_bronze"
      base_parameters = { env = "azure_dev" }
    }
  }

  # NOTE: task blocks are declared in ALPHABETICAL task_key order because the
  # provider reads them back from the API sorted that way. Declaring them in
  # DAG order produces a permanent, cosmetic diff on every plan. The real
  # execution order is bronze -> silver -> scd2 -> gold -> quality, defined by
  # the depends_on edges below, not by position in this file.

  task {
    task_key        = "gold"
    environment_key = "factorypulse_env"
    depends_on { task_key = "scd2" }

    notebook_task {
      notebook_path   = "${local.notebook_base}/13_gold"
      base_parameters = { env = "azure_dev" }
    }
  }

  task {
    task_key        = "quality"
    environment_key = "factorypulse_env"
    depends_on { task_key = "gold" }

    notebook_task {
      notebook_path   = "${local.notebook_base}/14_quality"
      base_parameters = { env = "azure_dev" }
    }
  }

  task {
    task_key        = "scd2"
    environment_key = "factorypulse_env"
    depends_on { task_key = "silver" }

    notebook_task {
      notebook_path   = "${local.notebook_base}/12_scd2"
      base_parameters = { env = "azure_dev" }
    }
  }

  task {
    task_key        = "silver"
    environment_key = "factorypulse_env"
    depends_on { task_key = "bronze" }

    notebook_task {
      notebook_path   = "${local.notebook_base}/11_silver"
      base_parameters = { env = "azure_dev" }
    }
  }

  schedule {
    quartz_cron_expression = "0 0 2 * * ?"
    timezone_id            = "Europe/Berlin"
    pause_status           = "PAUSED"
  }
}

output "databricks_job_id" {
  value = var.enable_databricks ? databricks_job.medallion[0].id : null
}

output "databricks_job_url" {
  value = var.enable_databricks ? "${local.dbw_url}/jobs/${databricks_job.medallion[0].id}" : null
}
