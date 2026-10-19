variable "subscription_id" {
  description = "Azure subscription ID."
  type        = string
}

variable "location" {
  description = "Azure region for all project resources."
  type        = string
  default     = "germanywestcentral"
}

variable "project" {
  description = "Project prefix used for resource names."
  type        = string
  default     = "factorypulse"
}

variable "environment" {
  description = "Deployment environment."
  type        = string
  default     = "dev"
}

variable "my_ip" {
  description = "Public IPv4 address allowed through the Azure SQL firewall."
  type        = string
}

variable "alert_email" {
  description = "Budget and monitoring alert recipient."
  type        = string
}

variable "budget_amount" {
  description = "Main monthly budget in subscription currency."
  type        = number
  default     = 200
}

variable "canary_budget_amount" {
  description = "Early-warning monthly budget in subscription currency."
  type        = number
  default     = 30
}

variable "sql_admin_user" {
  description = "Azure SQL administrator login."
  type        = string
  default     = "fpadmin"
}

variable "enable_data_factory" {
  description = "Create Data Factory and its ingestion resources."
  type        = bool
  default     = true
}

variable "enable_databricks" {
  description = "Create the Azure Databricks workspace and Unity Catalog resources."
  type        = bool
  default     = true
}

variable "databricks_sku" {
  description = "Azure Databricks tier. Standard was retired on 2026-10-01."
  type        = string
  default     = "premium"

  validation {
    condition     = lower(var.databricks_sku) == "premium"
    error_message = "Use premium: Azure Databricks Standard was retired on 2026-10-01."
  }
}

variable "cluster_autotermination_minutes" {
  description = "Idle minutes before the interactive cluster terminates."
  type        = number
  default     = 10

  validation {
    condition     = var.cluster_autotermination_minutes >= 10 && var.cluster_autotermination_minutes <= 30
    error_message = "Azure Databricks permits a minimum of 10 minutes; keep the value at or below 30."
  }
}

variable "databricks_node_type" {
  description = "Small single-node Azure VM SKU used for the short validation run."
  type        = string
  default     = "Standard_D4as_v5"
}

variable "enable_classic_databricks_cluster" {
  description = "Create classic VM compute. Keep false when Azure VM quota/capacity is constrained."
  type        = bool
  default     = false
}

variable "workspace_admin_email" {
  description = "Databricks login email used for job failure notifications."
  type        = string
}


variable "wheel_version" {
  description = "Version of the factorypulse wheel to install on job compute. MUST match [project].version in pyproject.toml."
  type        = string
  default     = "0.1.8"
}
