data "azurerm_client_config" "current" {}

resource "azurerm_resource_group" "main" {
  name     = local.rg_name
  location = var.location
  tags     = local.tags

  depends_on = [
    azurerm_consumption_budget_subscription.main,
    azurerm_consumption_budget_subscription.canary,
  ]
}

resource "azurerm_storage_account" "lake" {
  name                     = local.storage_name
  resource_group_name      = azurerm_resource_group.main.name
  location                 = azurerm_resource_group.main.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = true

  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

resource "azurerm_role_assignment" "tf_storage" {
  scope                = azurerm_storage_account.lake.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = data.azurerm_client_config.current.object_id
}

resource "time_sleep" "wait_storage_rbac" {
  depends_on      = [azurerm_role_assignment.tf_storage]
  create_duration = "120s"
}

resource "azurerm_storage_data_lake_gen2_filesystem" "lake" {
  name               = "lake"
  storage_account_id = azurerm_storage_account.lake.id
  depends_on         = [time_sleep.wait_storage_rbac]
}

resource "azurerm_storage_data_lake_gen2_path" "dirs" {
  for_each = toset(local.lake_directories)

  path               = each.value
  filesystem_name    = azurerm_storage_data_lake_gen2_filesystem.lake.name
  storage_account_id = azurerm_storage_account.lake.id
  resource           = "directory"
}
