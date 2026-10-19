resource "azurerm_databricks_workspace" "main" {
  count = var.enable_databricks ? 1 : 0

  name                        = local.dbw_name
  resource_group_name         = azurerm_resource_group.main.name
  managed_resource_group_name = "databricks-rg-${var.project}-${var.environment}"
  location                    = azurerm_resource_group.main.location
  sku                         = var.databricks_sku

  tags = local.tags
}

resource "azurerm_databricks_access_connector" "main" {
  count = var.enable_databricks ? 1 : 0

  name                = "ac-${var.project}-${var.environment}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

resource "azurerm_role_assignment" "uc_storage" {
  count = var.enable_databricks ? 1 : 0

  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azurerm_databricks_access_connector.main[0].identity[0].principal_id
}

resource "time_sleep" "wait_uc_rbac" {
  count           = var.enable_databricks ? 1 : 0
  depends_on      = [azurerm_role_assignment.uc_storage]
  create_duration = "60s"
}

locals {
  dbw_url = var.enable_databricks ? "https://${azurerm_databricks_workspace.main[0].workspace_url}" : null
}
