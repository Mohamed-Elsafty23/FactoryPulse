resource "azurerm_data_factory" "main" {
  count = var.enable_data_factory ? 1 : 0

  name                = local.adf_name
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name

  identity {
    type = "SystemAssigned"
  }

  tags = local.tags
}

locals {
  adf_id           = var.enable_data_factory ? azurerm_data_factory.main[0].id : null
  adf_principal_id = var.enable_data_factory ? azurerm_data_factory.main[0].identity[0].principal_id : null
}

resource "azurerm_role_assignment" "adf_storage" {
  count = var.enable_data_factory ? 1 : 0

  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = local.adf_principal_id
}

resource "azurerm_role_assignment" "adf_keyvault" {
  count = var.enable_data_factory ? 1 : 0

  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = local.adf_principal_id
}

resource "time_sleep" "wait_adf_rbac" {
  count = var.enable_data_factory ? 1 : 0

  depends_on = [
    azurerm_role_assignment.adf_storage,
    azurerm_role_assignment.adf_keyvault,
  ]
  create_duration = "90s"
}
